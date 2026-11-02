"""The maintenance assistant: a GraphRAG Consumer of the plant Knowledge Graph.

It answers the shift lead's questions as text-to-Cypher. The Ontology Version it uses,
fetched from stetiq as YAML, goes into Claude's prompt; Claude writes one read-only
Cypher query; the production graph runs it in a read transaction; Claude answers from
the rows. Every answer carries the Cypher it ran and the work orders in its rows.

Without Claude (no `ANTHROPIC_API_KEY`, or the API unreachable) the scripted questions
answer from `recordings/answers.json`, keyed by question and Ontology Version, and
free-form questions are refused.

    cd showcase/plant-assistant
    uv run uvicorn plant_assistant.assistant:app_from_env --factory --port 8000

reads `STETIQ_TRACKING_URI` / `STETIQ_TOKEN` (stetiq), `PLANT_PRODUCTION_URI` with
`NEO4J_USER` / `NEO4J_PASSWORD` (the production graph) and `ANTHROPIC_API_KEY`.

The Connector guard decides which Ontology Version is in use. It polls stetiq on startup
and every 5 s, through stetiq's public client calls only. The first time, it takes the
version the `production` Contract Alias points to: nothing is in use yet, so there is
nothing to protect. After that a version is *on offer* when `production` points to
another version than the one in use, or else when the latest Candidate is newer than it.
The guard reads the assistant's latest recorded Consumer Gate result for the version on
offer:

- passed, and `production` points to it: switch to it (`accepted`);
- passed, but `production` does not point to it yet: stay (`waiting`), since the
  assistant answers from the production graph;
- failed, or no verdict recorded: stay (`refused`), naming the symptom the verdict gives
  (each failing question and its row change), or "no Consumer Gate verdict".

The last decision stays on the banner until another version is on offer.

The guard can be turned off, for the act that shows the show without stetiq. Off, it
follows whatever is deployed: the pipeline's CD then deploys every run, so the assistant
takes the newest Ontology Version stetiq holds (the latest Candidate when it is newer
than the version `production` points to), asking for no verdict.

HTTP API:
- `GET /api/status`: `{in_use, offered, decision, reason, guard, banner, free_form,
  message}`:
  the Ontology Version in use (null before stetiq has a Contract version), the version on
  offer and the guard's decision on it (`accepted`, `waiting` or `refused`; nulls before
  any offer) with its reason, the banner the chat page shows, and whether free-form
  questions are answered;
- `POST /api/ask` `{question}`: `{question, answer, cypher, work_orders,
  ontology_version, source}`, `source` being `live` (Claude) or `recorded`;
- `POST /api/poll`: check stetiq now instead of waiting for the next poll; returns the
  status;
- `POST /api/reset` `{guard}`: forget the version in use and the guard's last decision,
  as a restart would, with the guard `on` or `off`; returns the status. The show calls it
  when it rewinds stetiq, whose versions and verdicts the assistant's state refers to.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, LiteralString, Protocol, cast

import neo4j
import neo4j.exceptions
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import stetiq

KG = "plant-maintenance"
CONSUMER = "maintenance-assistant"  # the assistant's Consumer id in the Use Case
MODEL = "claude-sonnet-5-5"
PRODUCTION_DATABASE = "neo4j"  # Neo4j Community has the one database
POLL_SECONDS = 5.0
RECORDINGS = Path(__file__).resolve().parent.parent / "recordings" / "answers.json"
PAGE = Path(__file__).resolve().parent / "static" / "index.html"
ROW_LIMIT = 200  # rows past this are not sent to Claude
NO_KEY = (
    "Free-form questions are off: the assistant has no ANTHROPIC_API_KEY, so it answers "
    "only the scripted questions, from recorded answers."
)

_WORK_ORDER_ID = re.compile(r"\bWO-\d{4}\b")

_CYPHER_SYSTEM = """You answer questions about a factory's maintenance history from its \
Neo4j knowledge graph. The graph follows the Ontology below (Ontology Version {number}, \
YAML): its node types, properties, relationship types and patterns are all the graph \
holds. Write exactly one read-only Cypher query (MATCH ... RETURN; never CREATE, MERGE, \
SET, DELETE, REMOVE or CALL) that fetches the rows needed to answer the question. Use only \
labels, properties and values the Ontology declares; where it lists a property's allowed \
values, filter on those. Return readable columns (ids, names, descriptions). If the \
Ontology cannot answer the question, return a query for the closest rows it does hold.

{ontology}"""

_ANSWER_SYSTEM = """You are the maintenance assistant for a factory's shift lead. You \
answer from rows a Cypher query returned from the plant's knowledge graph, which follows \
the Ontology below (Ontology Version {number}, YAML). Answer in two to four plain \
sentences, naming machines and work order ids. Use only the rows; if the Ontology has no \
concept for what was asked, say the graph does not record it. Do not mention Cypher.

{ontology}"""

_CYPHER_FORMAT = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"cypher": {"type": "string"}},
        "required": ["cypher"],
        "additionalProperties": False,
    },
}

try:  # the Anthropic SDK is only needed when Claude answers live
    import anthropic

    _API_ERRORS: tuple[type[Exception], ...] = (anthropic.APIError,)
except ImportError:  # pragma: no cover - the showcase installs it
    _API_ERRORS = ()


class Claude(Protocol):
    """What the assistant needs of `anthropic.Anthropic()` (tests pass a scripted fake)."""

    @property
    def beta(self) -> Any: ...


@dataclass(frozen=True)
class Recording:
    """A recorded answer to a scripted question on one Ontology Version."""

    question: str
    ontology_version: int
    cypher: str
    answer: str


@dataclass(frozen=True)
class Answer:
    question: str
    answer: str
    cypher: str
    work_orders: list[str]
    ontology_version: int
    source: str  # live | recorded


Decision = Literal["accepted", "waiting", "refused"]
Guard = Literal["on", "off"]


class Refused(Exception):
    """A question the assistant will not answer; `status` is the HTTP status it sends."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def load_recordings(path: Path = RECORDINGS) -> dict[tuple[str, int], Recording]:
    entries = json.loads(path.read_text())["answers"]
    return {
        (_normal(e["question"]), e["ontology_version"]): Recording(
            e["question"], e["ontology_version"], e["cypher"], e["answer"]
        )
        for e in entries
    }


def _normal(question: str) -> str:
    return " ".join(
        question.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").split()
    ).rstrip("?")


class Assistant:
    """The assistant's state: the Ontology Version in use and how it answers.

    `stetiq` is the assistant's own client (a read token is enough); `production` is the
    production graph. `llm` is the Anthropic client, or None to answer from recordings
    only."""

    def __init__(
        self,
        stetiq_client: stetiq.Client,
        production: neo4j.Driver,
        *,
        llm: Claude | None,
        recordings: dict[tuple[str, int], Recording] | None = None,
        knowledge_graph: str = KG,
        consumer: str = CONSUMER,
        model: str = MODEL,
        guard: Guard = "on",
    ) -> None:
        self.stetiq = stetiq_client
        self.production = production
        self.llm = llm
        self.recordings = load_recordings() if recordings is None else recordings
        self.knowledge_graph = knowledge_graph
        self.consumer = consumer
        self.model = model
        self.guard: Guard = guard
        self.in_use: int | None = None
        self.ontology_yaml: str | None = None
        # The Connector guard's last decision: the version on offer, and why.
        self.offered: int | None = None
        self.decision: Decision | None = None
        self.reason: str | None = None
        self._lock = threading.Lock()

    # --- The Ontology Version in use ------------------------------------------------

    def poll(self) -> None:
        """The Connector guard: look for a version on offer and decide whether to take
        it (see the module docstring). While stetiq is unreachable, or before it has a
        Contract version, nothing changes."""
        kg = self.knowledge_graph
        try:
            production = self.stetiq.get_contract_version(kg).number
            if self.guard == "off":
                self._follow(max(production, self.stetiq.latest_candidate(kg).number))
                return
            if self.in_use is None:
                self._take(production)
                return
            if production != self.in_use:
                offered = production
            else:
                candidate = self.stetiq.latest_candidate(kg).number
                if candidate <= self.in_use:
                    return  # nothing new on offer: the last decision stands
                offered = candidate
            decision, reason = self._judge(offered, in_production=offered == production)
            if decision == "accepted":
                self._take(offered)
        except stetiq.StetiqError:
            return
        with self._lock:
            self.offered, self.decision, self.reason = offered, decision, reason

    def _judge(self, version: int, *, in_production: bool) -> tuple[Decision, str | None]:
        """The guard's decision on `version`, from the assistant's latest recorded
        Consumer Gate result for it."""
        results = self.stetiq.list_consumer_gate_results(
            self.knowledge_graph, consumer=self.consumer, version=version
        )
        if not results:
            return "refused", "no Consumer Gate verdict"
        verdict = results[-1]
        if not verdict.passed:
            return "refused", _symptom(verdict)
        if not in_production:
            return "waiting", "Consumer Gate passed, not in production yet"
        return "accepted", None

    def _follow(self, version: int) -> None:
        """The guard off: take `version` without a verdict; there is no decision."""
        if version != self.in_use:
            self._take(version)
        with self._lock:
            self.offered = self.decision = self.reason = None

    def reset(self, guard: Guard) -> None:
        """Forget the version in use and the guard's last decision, and set the guard."""
        with self._lock:
            self.guard = guard
            self.in_use = self.ontology_yaml = None
            self.offered = self.decision = self.reason = None

    def _take(self, version: int) -> None:
        ontology_yaml = self.stetiq.get_ontology_yaml(self.knowledge_graph, version)
        with self._lock:
            self.in_use, self.ontology_yaml = version, ontology_yaml

    def status(self) -> dict[str, Any]:
        with self._lock:
            in_use, offered = self.in_use, self.offered
            decision, reason = self.decision, self.reason
        return {
            "in_use": in_use,
            "offered": offered,
            "decision": decision,
            "reason": reason,
            "guard": self.guard,
            "banner": _banner(in_use, offered, decision, reason),
            "free_form": self.llm is not None,
            "message": None if self.llm is not None else NO_KEY,
        }

    # --- Answering ------------------------------------------------------------------

    def ask(self, question: str) -> Answer:
        with self._lock:
            number, ontology_yaml = self.in_use, self.ontology_yaml
        if number is None or ontology_yaml is None:
            raise Refused(503, "The assistant has no Ontology Version yet: nothing is deployed.")
        recording = self.recordings.get((_normal(question), number))
        if self.llm is not None:
            try:
                return self._ask_claude(self.llm, question, number, ontology_yaml)
            except _API_ERRORS:
                if recording is None:
                    raise Refused(
                        503, "Claude is unreachable, and this question has no recorded answer."
                    ) from None
        if recording is None:
            raise Refused(503, NO_KEY)
        rows = self._run(recording.cypher)
        return Answer(
            question, recording.answer, recording.cypher, _work_orders(rows), number, "recorded"
        )

    def _ask_claude(self, llm: Claude, question: str, number: int, ontology_yaml: str) -> Answer:
        reply = self._create(
            llm,
            system=_CYPHER_SYSTEM.format(number=number, ontology=ontology_yaml),
            content=f"Question: {question}",
            output_config={"effort": "low", "format": _CYPHER_FORMAT},
        )
        cypher = json.loads(reply)["cypher"]
        rows = self._run(cypher)
        shown = json.dumps(rows[:ROW_LIMIT], default=str, ensure_ascii=False)
        answer = self._create(
            llm,
            system=_ANSWER_SYSTEM.format(number=number, ontology=ontology_yaml),
            content=f"Question: {question}\n\nCypher:\n{cypher}\n\nRows ({len(rows)}):\n{shown}",
            output_config={"effort": "low"},
        )
        return Answer(question, answer, cypher, _work_orders(rows), number, "live")

    def _create(self, llm: Claude, *, system: str, content: str, output_config: dict) -> str:
        response = llm.beta.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config=output_config,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise Refused(422, "Claude declined to answer this question.")
        return "".join(b.text for b in response.content if b.type == "text")

    def _run(self, cypher: str) -> list[dict[str, Any]]:
        """Run `cypher` on the production graph in a read transaction: the server
        rejects any write in it."""

        def work(tx: neo4j.ManagedTransaction) -> list[dict[str, Any]]:
            return [r.data() for r in tx.run(cast(LiteralString, cypher))]

        try:
            with self.production.session(database=PRODUCTION_DATABASE) as session:
                return session.execute_read(work)
        except neo4j.exceptions.ClientError as e:
            if "write" in (e.message or "").lower():
                raise Refused(
                    422, "The generated Cypher tried to write; the assistant runs read-only."
                ) from None
            raise Refused(422, f"The generated Cypher failed: {e.code}") from None


def _symptom(verdict: stetiq.ConsumerGateResult) -> str:
    """What a failed verdict names, from its findings: each failing question and its row
    change, or the input that was missing. Never a cause: stetiq reads no instance data."""
    symptoms = [
        f"{f.competency_question} {percent(f.change)}"
        if f.change is not None
        else f"{f.competency_question} {f.missing}"
        for o in verdict.failed
        for f in o.findings
    ]
    return ", ".join(symptoms) or "Consumer Gate failed"


def percent(change: float) -> str:
    """A relative row change as the verdict lines and the banner write it, with a minus sign."""
    sign = "\N{MINUS SIGN}" if change < 0 else "+"
    return f"{sign}{abs(change) * 100:.0f}%"


def _banner(
    in_use: int | None, offered: int | None, decision: Decision | None, reason: str | None
) -> str:
    """The chat page's banner: the version in use and the guard's last decision."""
    if in_use is None:
        return "no Ontology Version yet"
    banner = f"on Ontology v{in_use}"
    if decision == "accepted" and offered == in_use:
        return f"{banner} · accepted"
    if decision is not None:
        return f"{banner} · v{offered} offered: {decision} ({reason})"
    return banner


def _work_orders(rows: list[dict[str, Any]]) -> list[str]:
    """The work order ids in the rows, in order of first appearance."""
    found: dict[str, None] = {}
    for row in rows:
        for value in row.values():
            for wo in _WORK_ORDER_ID.findall(json.dumps(value, default=str)):
                found.setdefault(wo, None)
    return list(found)


# --- The HTTP API -------------------------------------------------------------------


class Question(BaseModel):
    question: str


class Reset(BaseModel):
    guard: Guard = "on"


def create_app(assistant: Assistant, *, poll_interval: float | None = POLL_SECONDS) -> FastAPI:
    """The assistant's app. It polls stetiq on startup and then every `poll_interval`
    seconds (None: only on startup and on `POST /api/poll`)."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        assistant.poll()
        stop = threading.Event()
        if poll_interval is not None:

            def loop() -> None:
                while not stop.wait(poll_interval):
                    assistant.poll()

            threading.Thread(target=loop, name="stetiq-poll", daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="Maintenance assistant", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE.read_text()

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return assistant.status()

    @app.post("/api/poll")
    def poll() -> dict[str, Any]:
        assistant.poll()
        return assistant.status()

    @app.post("/api/reset")
    def reset(body: Reset) -> dict[str, Any]:
        assistant.reset(body.guard)
        return assistant.status()

    @app.post("/api/ask")
    def ask(body: Question) -> dict[str, Any]:
        try:
            answer = assistant.ask(body.question)
        except Refused as e:
            raise HTTPException(e.status, str(e)) from None
        return asdict(answer)

    return app


def app_from_env() -> FastAPI:
    """The app as compose runs it, configured from the environment."""
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    production = neo4j.GraphDatabase.driver(
        os.environ.get("PLANT_PRODUCTION_URI", "bolt://localhost:7688"), auth=auth
    )
    llm = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        llm = anthropic.Anthropic()
    return create_app(Assistant(stetiq.Client(), production, llm=llm))
