"""The plant-assistant show: a GraphRAG Consumer that stetiq keeps honest.

    cd showcase/plant-assistant
    uv run python show.py              # replays the recorded Claude extraction rounds
    uv run python show.py --live       # calls Claude (the `claude` CLI) on a cache miss
    uv run python show.py --act 2      # starts at the beginning of Act 2
    uv run python show.py --reset      # rewinds stetiq, both graphs and the assistant
    uv run python show.py --epilogue   # after Act 3, a hand edit to production: Drift
    uv run python show.py --no-pause   # straight through, without waiting for Enter

The show pauses for Enter at each beat the audience sees (each act, each scripted
question), and checks every container before each act, naming any that is down.

stetiq is a remote server (`STETIQ_TRACKING_URI`, an API token in `STETIQ_TOKEN`); the
pipeline writes two Neo4j servers, the candidate graph every Construction Run builds
(`PLANT_CANDIDATE_URI`) and the production graph a promoted run is deployed to
(`PLANT_PRODUCTION_URI`), with `NEO4J_USER` / `NEO4J_PASSWORD`. The maintenance
assistant runs at `PLANT_ASSISTANT_URL`; the show asks it the scripted questions over
its HTTP API. Each one not set comes from the compose stack (docker-compose.yml): the
host ports and password in `.env`, and the token compose issued to `.show/tokens/show`.
README.md tells how to run it on stage; STORY.md tells the story and its running order.

The show is played twice from the start: once without stetiq (Acts 0 and 1), then, after
a rewind, with it (Acts 0, 2 and 3). The rewind empties stetiq's tracking database (its
API tokens are kept, so the server's clients stay signed in): inside the compose stack's
stetiq container, or at `STETIQ_DATABASE_URL` when that is set. It also empties both
graphs, and resets the assistant, with its
Connector guard off for the first pass and on for the second. `--act N` rewinds and
replays the acts before N, so it starts Act N from the state they leave.

Act 0, Monday morning: prompt v1 builds v1, the Gates pass, `production` is promoted
to v1 and the run is deployed. The assistant, on v1, answers both scripted questions.

Act 1, without stetiq: the assistant's guard is off, and the pipeline's CD deploys every
run its tests pass. Prompt v2 with Line 2's EAM export is deployed straight to the
production graph; the assistant follows it to v2, answers the suppliers question, and
says Line 2 had no breakdowns: its Cypher filters `kind = 'breakdown'`, and the EAM
export calls Line 2's two breakdowns `corrective`.

Act 2, with stetiq (after the rewind): prompt v2 with Line 2's EAM export passes every Gate but fails the
maintenance assistant's and the reliability dashboard's Consumer Gates, so it stays the
Candidate, unpromoted and undeployed. The assistant's Connector guard refuses v2, naming
the symptom, and the assistant stays on v1 and right.

Act 3, the fix: `WorkOrder.kind` bound to the `WorkOrderKind` Vocabulary passes the Gates
and the Consumer Gates; `production` moves to it and the run is deployed. The guard
accepts v3 on its next poll, and both scripted questions answer on it.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHOWCASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SHOWCASE_DIR))

from dataclasses import replace  # noqa: E402

import httpx  # noqa: E402
import neo4j  # noqa: E402
import neo4j.exceptions  # noqa: E402
import yaml  # noqa: E402
from plant_assistant.assistant import Guard, percent  # noqa: E402
from plant_assistant.deploy import PRODUCTION_DATABASE, deploy  # noqa: E402
from plant_assistant.evaluators import Documented, ReportCoverage  # noqa: E402
from plant_assistant.graph import Extraction  # noqa: E402
from plant_assistant.pipeline import (  # noqa: E402
    ExtractionError,
    LlmMode,
    Round,
    run_round,
)
from plant_assistant.rewind import rewind_tracking  # noqa: E402

import stetiq  # noqa: E402
from stetiq import CompetencyQuestion, GraphSourceScope  # noqa: E402
from stetiq.graph_source import Neo4jGraphSource  # noqa: E402

KG = "plant-maintenance"
CANDIDATE_DATABASE = "neo4j"  # Neo4j Community has the one database
CONFIG = SHOWCASE_DIR / "stetiq.yaml"
ONTOLOGY = SHOWCASE_DIR / "ontology"
USE_CASE = SHOWCASE_DIR / "use-case.yaml"

DESCRIPTION = """Maintenance history of the two production lines: **work orders** from the CMMS,
the **machines** and **lines** from the asset register, and what Claude reads out of the
technicians' free-text reports (components, root causes, follow-ups, part suppliers).

Built by the plant-assistant showcase's pipeline into Neo4j; the Consumers and their
Competency Questions are in `use-case.yaml`."""

ROUND_LABEL: dict[Round, str] = {"v1": "v1", "v2": "prompt v2", "fix": "fix"}
ACTS = (0, 1, 2, 3)
ACT_TITLES = {
    0: "Act 0, Monday morning",
    1: "Act 1, without stetiq",
    2: "Act 2, with stetiq",
    3: "Act 3, the fix",
}
REWIND = "Rewind: stetiq, both graphs and the assistant back to the start"

LINE_2 = "Why did Line 2's machines break down?"
SUPPLIERS = "Which suppliers' components keep failing?"
SCRIPTED_QUESTIONS = (LINE_2, SUPPLIERS)

# Before prompt v2, the assistant's root-cause Task also needs to know which suppliers'
# components keep failing: the reason prompt v2 may add Supplier (unjustified-additions).
PARTS_SUPPLIERS = CompetencyQuestion(
    id="parts-suppliers",
    question="Which suppliers' components keep failing?",
    query="MATCH (c:Component)-[:SUPPLIED_BY]->(s:Supplier) "
    "RETURN c.name AS component, s.name AS supplier",
)
PARTS_SUPPLIERS_TASK = "explain-root-causes"


@dataclass(frozen=True)
class Graphs:
    """The two Neo4j servers the pipeline writes: `candidate`, which every Construction
    Run rebuilds and stetiq observes, and `production`, which a deploy replays a
    promoted run into."""

    candidate: neo4j.Driver
    production: neo4j.Driver


@dataclass(frozen=True)
class Answer:
    """The assistant's answer to a question, as its HTTP API returned it."""

    question: str
    answer: str
    cypher: str
    work_orders: list[str]
    ontology_version: int
    source: str  # live (Claude) | recorded


@dataclass(frozen=True)
class ActState:
    """What one act did, as the audience sees it (`line`) and as stetiq recorded it."""

    act: int
    round: Round
    line: str  # the PR-style verdict line
    run: stetiq.ConstructionRun
    gates: stetiq.GateResult | None  # None in Act 1: without stetiq, no Gate runs
    promoted: bool
    deployed: bool
    # The Consumer Gate verdicts the act's CI asked for (none in Act 0, the baseline).
    consumer_gates: tuple[stetiq.ConsumerGateResult, ...] = ()
    # The run whose Extraction the production graph holds after the act.
    production_run: str | None = None
    # The assistant's status (`GET /api/status`: the version in use, the version on
    # offer and its Connector guard's decision) and its answers to the scripted
    # questions after the act (None and empty when the show runs without the assistant).
    status: dict[str, Any] | None = None
    answers: dict[str, Answer] = field(default_factory=dict)

    @property
    def banner(self) -> str | None:
        """The assistant's banner after the act, as its chat page shows it."""
        return None if self.status is None else self.status["banner"]


@dataclass
class ShowState:
    """The state the show builds up, act by act (the test reads it back)."""

    # The last time each act ran: Act 0 is the replay after the rewind, whose run the
    # tracking database still holds.
    acts: dict[int, ActState] = field(default_factory=dict)
    # Acts 0 and 1 as the first pass played them, before the rewind.
    without_stetiq: list[ActState] = field(default_factory=list)
    # Every run's Extraction, by run id: what a deploy replays into production.
    extractions: dict[str, Extraction] = field(default_factory=dict)
    # The run the production graph holds now (None: nothing deployed yet).
    production_run: str | None = None

    @property
    def lines(self) -> list[str]:
        return [a.line for a in self.acts.values()]


class Show:
    def __init__(
        self,
        client: stetiq.Client,
        graphs: Graphs,
        *,
        extraction: LlmMode,
        quiet: bool,
        rewind_tracking: Callable[[], None],
        assistant: httpx.Client | None = None,
        check: Callable[[], list[str]] | None = None,
        pause: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.graphs = graphs
        self.rewind_tracking = rewind_tracking
        self.assistant = assistant
        self.check = check
        self.pause = pause
        self.extraction: LlmMode = extraction
        self.quiet = quiet
        self.state = ShowState()
        self._evaluators_registered = False

    def say(self, *lines: str) -> None:
        if lines and not self.quiet:
            print(*lines, sep="\n", flush=True)

    def beat(self, label: str) -> None:
        """A beat the audience sees: the presenter talks, then presses Enter. A quiet
        replay has none."""
        if self.pause is not None and not self.quiet:
            self.pause(label)

    def ready(self, act: int) -> None:
        """Before `act`: every container the show needs is up, or `StackDown` names the
        ones that are not."""
        down = self.check() if self.check is not None else []
        if down:
            raise StackDown(down, act)

    def declare(self) -> None:
        """The Knowledge Graph, its v1 Ontology, its Use Case, and its Graph Source scope
        bound to the candidate graph. The pipeline's Evaluators are registered first, so
        `documented` judges v1 too."""
        client = self.client
        if not self._evaluators_registered:  # with this client, so once per show
            client.register_evaluator(Documented())
            client.register_evaluator(ReportCoverage())
            self._evaluators_registered = True
        client.create_knowledge_graph(KG, ontology=ONTOLOGY / "v1.yaml")
        client.set_knowledge_graph_description(KG, DESCRIPTION)
        client.bind_graph_source(KG, GraphSourceScope(database=CANDIDATE_DATABASE))
        client.register_use_case(KG, USE_CASE)

    def rewind(self, *, guard: Guard) -> None:
        """Back to the start: stetiq's tracking database emptied (its API tokens kept),
        both graphs emptied, the assistant reset with its Connector guard `guard`, and
        the Knowledge Graph declared again."""
        self.rewind_tracking()
        for driver, database in (
            (self.graphs.candidate, CANDIDATE_DATABASE),
            (self.graphs.production, PRODUCTION_DATABASE),
        ):
            driver.execute_query("MATCH (n) DETACH DELETE n", database_=database)
        self.state.production_run = None
        if self.assistant is not None:
            _json(self.assistant.post("/api/reset", json={"guard": guard}))
        self.declare()

    def play(self, start_act: int = 0) -> ShowState:
        """The show from the beginning of `start_act`: the acts before it replay first,
        from a rewind, so it starts from the state they leave."""
        if start_act not in ACTS:
            raise ValueError(f"the show has Acts {ACTS[0]} to {ACTS[-1]}, not {start_act}")
        quiet = self.quiet
        self.ready(start_act)
        if start_act <= 1:
            self.rewind(guard="off")
            self.quiet = quiet or start_act > 0
            act_0 = self.play_act(0, self.act_0)
            self.quiet = quiet
            self.state.without_stetiq = [act_0, self.play_act(1, self.act_1)]
            self.beat(REWIND)
            self.say("", REWIND)
            self.ready(2)
        self.rewind(guard="on")
        for number, act in ((0, self.act_0), (2, self.act_2), (3, self.act_3)):
            # Before `start_act`, an act replays without a word: the show starts after it.
            # Act 0 after the rewind always does: the audience saw it in the first pass.
            self.quiet = quiet or number == 0 or number < start_act
            self.play_act(number, act)
        self.quiet = quiet
        return self.state

    def play_act(self, number: int, act: Callable[[], ActState]) -> ActState:
        """`act`, once every container is up, after its beat."""
        self.ready(number)
        self.beat(ACT_TITLES[number])
        try:
            return act()
        except (*_UNREACHABLE, stetiq.StetiqError, AssistantError) as e:
            # A container that went down during the act: name it, not the error it caused.
            down = self.check() if self.check is not None else []
            if down:
                raise StackDown(down, number) from e
            raise

    def construct(self, round_: Round, *, ontology_version: int | None = None):
        built = run_round(
            self.client,
            KG,
            round_,
            candidate=self.graphs.candidate,
            ontology_version=ontology_version,
            mode=self.extraction,
        )
        self.state.extractions[built.run.id] = built.extraction
        return built.run

    def act_0(self) -> ActState:
        """Monday morning: prompt v1 builds v1, the Gates pass, `production` is promoted
        to v1, and the run is deployed."""
        run = self.construct("v1")
        gates = self.client.evaluate_gates(KG, CONFIG, run=run.id)
        promoted = gates.passed
        if promoted:
            self.client.set_alias(KG, "production", gates.ontology_version)
            deploy(self.graphs.production, self.state.extractions[run.id])
            self.state.production_run = run.id
        parts = [ROUND_LABEL["v1"], f"Gate {_mark(gates.passed)}"]
        if promoted:
            parts += [f"promoted: production -> v{gates.ontology_version}", "deployed"]
        line = "   ".join(parts)
        self.say("", ACT_TITLES[0], line)
        for o in gates.outcomes:
            if not o.passed:
                self.say(f"    Gate {o.gate.name} failed: {'; '.join(o.reasons[:3])}")
        act = ActState(
            0,
            "v1",
            line,
            run,
            gates,
            promoted,
            promoted,
            production_run=self.state.production_run,
        )
        return self.consult_assistant(act)

    def act_1(self) -> ActState:
        """Without stetiq: the guard is off, and the pipeline's CD deploys every run its
        tests pass. Prompt v2 with Line 2's EAM export goes straight to the production
        graph, and the assistant follows it. The Use Case is the one Act 2's pull
        request meets, suppliers question and all: only stetiq's part is missing."""
        self.declare_parts_suppliers()
        run = self.construct("v2")
        tested = run.status == "finished"
        if tested:
            deploy(self.graphs.production, self.state.extractions[run.id])
            self.state.production_run = run.id
        line = "   ".join(
            [ROUND_LABEL["v2"], f"tests {_mark(tested)}", *(["deployed"] if tested else [])]
        )
        self.say("", ACT_TITLES[1], line)
        act = ActState(
            1, "v2", line, run, None, False, tested, production_run=self.state.production_run
        )
        return self.consult_assistant(act)

    def consult_assistant(self, act: ActState) -> ActState:
        """Record `act`, with what the assistant shows after it: over its HTTP API only,
        ask it to check stetiq now (one poll of its Connector guard), then read its
        status and ask it the scripted questions."""
        if self.assistant is not None:
            status = _json(self.assistant.post("/api/poll"))
            self.say(f"  assistant: {status['banner']}")
            answers: dict[str, Answer] = {}
            for question in SCRIPTED_QUESTIONS:
                self.beat(f"ask: {question}")
                reply = _json(self.assistant.post("/api/ask", json={"question": question}))
                answers[question] = Answer(**reply)
                self.say(f"  Q: {question}", f"  A: {reply['answer']}")
            act = replace(act, status=status, answers=answers)
        self.state.acts[act.act] = act
        return act

    def declare_parts_suppliers(self) -> stetiq.UseCaseVersion:
        """Before prompt v2: the assistant's root-cause Task now also asks which
        suppliers' components keep failing."""
        current = self.client.get_use_case_version(KG).use_case
        consumers = tuple(
            replace(
                c,
                tasks=tuple(
                    replace(t, competency_questions=(*t.competency_questions, PARTS_SUPPLIERS.id))
                    if t.id == PARTS_SUPPLIERS_TASK
                    else t
                    for t in c.tasks
                ),
            )
            for c in current.consumers
        )
        return self.client.register_use_case(
            KG,
            replace(
                current,
                competency_questions=(*current.competency_questions, PARTS_SUPPLIERS),
                consumers=consumers,
            ),
        )

    def gate(self, act_number: int, round_: Round, run: stetiq.ConstructionRun) -> ActState:
        """The pipeline's CI with stetiq: the Gates and every Consumer Gate on the run;
        `production` is promoted, and the run deployed, only when all of them pass."""
        if run.candidate_version is not None:
            # The custom Ontology Version Evaluator (`documented`) on the new Candidate;
            # the built-ins ran when stetiq proposed it.
            self.client.evaluate(KG, run.candidate_version)
        gates = self.client.evaluate_gates(KG, CONFIG, run=run.id)
        consumer_gates = tuple(
            sorted(self.client.evaluate_consumer_gates(KG, run=run.id), key=lambda c: c.consumer)
        )
        promoted = gates.passed and all(c.passed for c in consumer_gates)
        if promoted:
            self.client.set_alias(KG, "production", gates.ontology_version)
            deploy(self.graphs.production, self.state.extractions[run.id])
            self.state.production_run = run.id
        return ActState(
            act_number,
            round_,
            _line(round_, gates, consumer_gates, promoted),
            run,
            gates,
            promoted,
            promoted,
            consumer_gates=consumer_gates,
            production_run=self.state.production_run,
        )

    def act_2(self) -> ActState:
        """With stetiq: the same pull request (prompt v2 and Line 2's EAM export) runs
        again, and its CI asks stetiq. Every Gate passes; the Consumer Gates fail, so
        the Candidate stays unpromoted and the production graph is not touched. The
        assistant's Connector guard refuses v2 and stays on v1."""
        self.declare_parts_suppliers()
        act = self.gate(2, "v2", self.construct("v2"))
        self.say("", ACT_TITLES[2], act.line)
        self.say(*_detail_lines(act))
        return self.consult_assistant(act)

    def act_3(self) -> ActState:
        """The fix: v1 plus what prompt v2 added, with `WorkOrder.kind` bound to the
        `WorkOrderKind` Vocabulary, registered as the next Ontology Version. Prompt v2
        runs on it; the Gates and the Consumer Gates pass, `production` moves to it and
        the run is deployed. The assistant's Connector guard accepts v3 on its next
        poll."""
        fix = self.client.register_ontology(KG, ONTOLOGY / "fix.yaml")
        act = self.gate(3, "fix", self.construct("fix", ontology_version=fix.number))
        self.say("", ACT_TITLES[3], act.line)
        self.say(*_detail_lines(act))
        return self.consult_assistant(act)


class AssistantError(Exception):
    """The maintenance assistant refused or failed a request the show made."""


def _json(response: httpx.Response) -> dict:
    if response.is_error:
        raise AssistantError(f"the assistant answered {response.status_code}: {response.text}")
    return response.json()


def _mark(passed: bool) -> str:
    return "✅" if passed else "❌"


def _line(
    round_: Round,
    gates: stetiq.GateResult,
    consumer_gates: tuple[stetiq.ConsumerGateResult, ...],
    promoted: bool,
) -> str:
    """One PR-style line: the Gate, the Consumer Gate (each failing Consumer with the
    symptom its verdict names: question, row counts, change), and what happened."""
    parts = [ROUND_LABEL[round_], f"Gate {_mark(gates.passed)}"]
    if consumer_gates:
        passed = all(c.passed for c in consumer_gates)
        consumer = f"Consumer Gate {_mark(passed)}"
        if not passed:
            failing = [
                f"{c.consumer} ❌ "
                + ", ".join(
                    f"{f.competency_question} {f.before} → {f.after}, {percent(f.change)}"
                    if f.change is not None
                    else f"{f.competency_question} {f.missing}"
                    for o in c.outcomes
                    for f in o.findings
                )
                for c in consumer_gates
                if not c.passed
            ]
            consumer += f" ({'; '.join(failing)})"
        parts.append(consumer)
    if promoted:
        parts += [f"promoted: production -> v{gates.ontology_version}", "deployed"]
    elif consumer_gates:
        parts.append(f"not promoted (Candidate stays at v{gates.ontology_version})")
    return "   ".join(parts)


def _detail_lines(act: ActState) -> list[str]:
    """Under the line: failed Gates, the Ontology Diff Gate's reasons, and every
    Consumer Gate's reasons."""
    lines = []
    for o in act.gates.outcomes if act.gates is not None else ():
        if not o.passed:
            lines.append(f"    Gate {o.gate.name} failed: {'; '.join(o.reasons[:3])}")
        elif o.gate.check == "ontology_diff" and o.reasons:
            lines.append(f"    Gate {o.gate.name}: {'; '.join(o.reasons)}")
    for c in act.consumer_gates:
        for o in c.outcomes:
            lines.append(
                f"    {c.consumer} {o.gate.name} {_mark(o.passed)}"
                + (f": {'; '.join(o.reasons)}" if o.reasons else "")
            )
    return lines


class StackDown(Exception):
    """A container the show needs is down; `down` names each, as compose does."""

    def __init__(self, down: list[str], act: int) -> None:
        self.down = down
        self.act = act
        names = ", ".join(down)
        super().__init__(
            f"{names} {'is' if len(down) == 1 else 'are'} down: start "
            f"{'it' if len(down) == 1 else 'them'} with `docker compose up -d "
            f"{' '.join(down)}`, then `uv run python show.py --act {act}`"
        )


# What a probe raises when its container does not answer.
_UNREACHABLE: tuple[type[Exception], ...] = (
    OSError,
    httpx.HTTPError,
    neo4j.exceptions.DriverError,
    neo4j.exceptions.Neo4jError,
)


def stack_check(
    *, stetiq: httpx.Client, graphs: Graphs, assistant: httpx.Client
) -> Callable[[], list[str]]:
    """The check the show runs before each act: it returns the compose services that do
    not answer (none when the stack is up). `stetiq` and `assistant` are HTTP clients on
    the stetiq server's and the assistant's base URLs."""

    def http(client: httpx.Client, path: str) -> Callable[[], object]:
        return lambda: client.get(path).raise_for_status()

    probes: dict[str, Callable[[], object]] = {
        "stetiq": http(stetiq, "/health"),
        "graph-candidate": graphs.candidate.verify_connectivity,
        "graph-production": graphs.production.verify_connectivity,
        "assistant": http(assistant, "/api/status"),
    }

    def check() -> list[str]:
        down = []
        for service, probe in probes.items():
            try:
                probe()
            except _UNREACHABLE:
                down.append(service)
        return down

    return check


def presenter_pause(
    *, interactive: bool, read: Callable[[str], object] = input
) -> Callable[[str], None]:
    """The presenter's pause at a beat: wait for Enter (`read`) when `interactive`, never
    otherwise. When the input ends (Enter piped in, then EOF), the show carries on."""

    def pause(label: str) -> None:
        if not interactive:
            return
        with contextlib.suppress(EOFError):
            read(f"\n  [Enter] {label} ")
        if read is input and not sys.stdin.isatty():
            print()  # piped Enter is not echoed: end the prompt's line

    return pause


# --- The epilogue: a hand edit to the production graph shows up as Drift ----------------

EPILOGUE_TITLE = "Epilogue, a hand edit to graph-production"
# The spare parts someone adds to the production graph by hand: a type no Ontology
# Version declares.
SPARE_PARTS = (
    {"name": "Spindle bearing 6205-2RS", "stock": 2},
    {"name": "Hydraulic hose DN13", "stock": 4},
    {"name": "Chuck valve 5/2", "stock": 1},
)


@dataclass(frozen=True)
class Epilogue:
    """What the epilogue did to the production graph, and the Observation of it."""

    spare_parts_added: int
    follow_ups_deleted: int
    outcome: stetiq.ObservationOutcome
    line: str
    details: tuple[str, ...]


def hand_edit(production: neo4j.Driver) -> tuple[int, int]:
    """Someone edits the production graph by hand: adds `SparePart` nodes and deletes the
    follow-ups that are done. Returns the nodes added and deleted."""
    _, added, _ = production.execute_query(
        "UNWIND $parts AS part CREATE (p:SparePart) SET p = part",
        parts=list(SPARE_PARTS),
        database_=PRODUCTION_DATABASE,
    )
    _, deleted, _ = production.execute_query(
        "MATCH (f:FollowUp {status: 'done'}) DETACH DELETE f", database_=PRODUCTION_DATABASE
    )
    return added.counters.nodes_created, deleted.counters.nodes_deleted


def run_epilogue(
    observer: stetiq.Client,
    production: neo4j.Driver,
    *,
    quiet: bool = False,
    pause: Callable[[str], None] | None = None,
) -> Epilogue:
    """The optional epilogue, after Act 3: the hand edit, then an Observation of the
    production graph (`observer`'s Graph Source must be `production`) with the Drift
    thresholds of `stetiq.yaml`. stetiq compares it with the `production` Contract
    Alias's Ontology Version (structural Drift) and with the previous Observation
    (statistical Drift), and records any Drift event."""
    if pause is not None and not quiet:
        pause(EPILOGUE_TITLE)
    added, deleted = hand_edit(production)
    thresholds = stetiq.DriftThresholds.from_dict(yaml.safe_load(CONFIG.read_text())["drift"])
    outcome = observer.observe(KG, thresholds=thresholds)
    edit = f"hand edit: +{added} SparePart, \N{MINUS SIGN}{deleted} done FollowUp"
    drift = outcome.drift
    if drift is None:
        line, details = f"{edit}   No Drift", ()
    else:
        line = (
            f"{edit}   Drift ⚠ against {drift.contract_alias} -> v{drift.ontology_version} "
            f"({len(drift.structural)} structural, {len(drift.statistical)} statistical)"
        )
        details = tuple(
            f"    {f.kind.value:<15} {f.subject}  {f.detail}".rstrip() for f in drift.findings
        )
    if not quiet:
        print("", EPILOGUE_TITLE, line, *details, sep="\n", flush=True)
    return Epilogue(added, deleted, outcome, line, details)


def run_show(
    client: stetiq.Client,
    graphs: Graphs,
    *,
    rewind_tracking: Callable[[], None],
    extraction: LlmMode = "replay",
    quiet: bool = False,
    assistant: httpx.Client | None = None,
    start_act: int = 0,
    check: Callable[[], list[str]] | None = None,
    pause: Callable[[str], None] | None = None,
) -> ShowState:
    """Run the show headless: Acts 0 and 1 without stetiq, the rewind, then Acts 0, 2
    and 3 with it; or from the beginning of `start_act` (the acts before it replay
    first).

    `rewind_tracking` empties the stetiq server's tracking database, keeping its API
    tokens (e.g. `lambda: rewind_tracking(database_url)`); each rewind also empties
    both graphs and resets the assistant.

    `client` reaches the stetiq server and observes the candidate graph: its Graph Source
    must be `graphs.candidate` (e.g. `Neo4jGraphSource(graphs.candidate)`). `extraction`
    is how Claude's extraction runs: `replay` (the committed llm-cache/ only; a miss is
    an error), `live` (Claude on a miss) or `record` (Claude for every report).

    `assistant` is an HTTP client on the maintenance assistant's base URL (an
    `httpx.Client(base_url=...)`, or a FastAPI TestClient over its app); after an act
    the show reads its banner and asks it the scripted questions, over its HTTP API
    only.

    `check` (e.g. `stack_check(...)`) runs before the show and before each act; when it
    names a container that is down, the show stops with `StackDown`. `pause` is called
    at each beat the audience sees (e.g. `presenter_pause(...)`), never in a quiet
    replay."""
    show = Show(
        client,
        graphs,
        extraction=extraction,
        quiet=quiet,
        rewind_tracking=rewind_tracking,
        assistant=assistant,
        check=check,
        pause=pause,
    )
    return show.play(start_act)


# --- On stage: show.py against the compose stack ----------------------------------------

ENV_FILE = SHOWCASE_DIR / ".env"
# The edit token compose's `tokens` service issues for the show once the server is up.
TOKEN_FILE = SHOWCASE_DIR / ".show" / "tokens" / "show"
REWIND_SCRIPT = SHOWCASE_DIR / "plant_assistant" / "rewind.py"


class RewindError(Exception):
    """The rewind inside the stetiq container failed."""


def _dotenv(path: Path = ENV_FILE) -> dict[str, str]:
    """The `KEY=value` lines of compose's `.env` (no quoting, no interpolation)."""
    if not path.exists():
        return {}
    pairs = (
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    return {key.strip(): value.strip() for key, value in pairs}


def stage_settings(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Where show.py finds the stack: the environment, else what compose's `.env` sets up
    (its host ports and the Neo4j password), and the token compose issued for the show."""
    env = dict(os.environ if environ is None else environ)
    dotenv = _dotenv()

    def port(name: str, default: str) -> str:
        return env.get(name) or dotenv.get(name) or default

    token = env.get("STETIQ_TOKEN") or (
        TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
    )
    return {
        "STETIQ_TRACKING_URI": env.get("STETIQ_TRACKING_URI")
        or f"http://localhost:{port('STETIQ_PORT', '5000')}",
        "STETIQ_TOKEN": token,
        "PLANT_CANDIDATE_URI": env.get("PLANT_CANDIDATE_URI")
        or f"bolt://localhost:{port('CANDIDATE_PORT', '7687')}",
        "PLANT_PRODUCTION_URI": env.get("PLANT_PRODUCTION_URI")
        or f"bolt://localhost:{port('PRODUCTION_PORT', '7688')}",
        "PLANT_ASSISTANT_URL": env.get("PLANT_ASSISTANT_URL")
        or f"http://localhost:{port('ASSISTANT_PORT', '8000')}",
        "NEO4J_USER": env.get("NEO4J_USER") or "neo4j",
        "NEO4J_PASSWORD": env.get("NEO4J_PASSWORD") or dotenv.get("NEO4J_PASSWORD", ""),
        "STETIQ_DATABASE_URL": env.get("STETIQ_DATABASE_URL", ""),
    }


def rewind_in_container() -> None:
    """The rewind as compose runs it: inside the stetiq container, on the SQLite file in
    its volume, next to the server that holds it open (the host never opens that file)."""
    try:
        done = subprocess.run(
            ["docker", "compose", "exec", "-T", "stetiq", "python", "-"],
            input=REWIND_SCRIPT.read_text(),
            text=True,
            capture_output=True,
            cwd=SHOWCASE_DIR,
            check=False,
        )
    except FileNotFoundError:
        raise RewindError("the rewind needs the docker CLI on the PATH") from None
    if done.returncode != 0:
        raise RewindError(f"the rewind in the stetiq container failed: {done.stderr.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--live",
        action="store_true",
        help="call the claude CLI on a cache miss, caching to the gitignored .show/llm-cache/",
    )
    modes.add_argument(
        "--record",
        action="store_true",
        help="call the claude CLI for every report and overwrite the committed llm-cache/",
    )
    start = parser.add_mutually_exclusive_group()
    start.add_argument(
        "--act",
        type=int,
        choices=ACTS,
        default=0,
        help="start at the beginning of this act (the acts before it replay without a word)",
    )
    start.add_argument(
        "--reset",
        action="store_true",
        help="only rewind: stetiq, both graphs and the assistant back to the start",
    )
    parser.add_argument(
        "--epilogue",
        action="store_true",
        help="after Act 3, hand-edit the production graph and observe it: Drift",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="run straight through without waiting for Enter at each beat",
    )
    args = parser.parse_args(argv)
    # The driver's retry warnings while a Neo4j container is down: the stack check names it.
    logging.getLogger("neo4j").setLevel(logging.ERROR)
    mode: LlmMode = "record" if args.record else "live" if args.live else "replay"
    settings = stage_settings()
    if not settings["STETIQ_TOKEN"]:
        print(
            f"error: no API token: set STETIQ_TOKEN, or run `docker compose up`, which "
            f"issues one to {TOKEN_FILE.relative_to(SHOWCASE_DIR)}",
            file=sys.stderr,
        )
        return 2
    database_url = settings["STETIQ_DATABASE_URL"]
    rewind = (lambda: rewind_tracking(database_url)) if database_url else rewind_in_container
    pause = presenter_pause(interactive=not args.no_pause)
    auth = (settings["NEO4J_USER"], settings["NEO4J_PASSWORD"])
    tracking_uri = settings["STETIQ_TRACKING_URI"]
    with (
        neo4j.GraphDatabase.driver(
            settings["PLANT_CANDIDATE_URI"], auth=auth, max_transaction_retry_time=5
        ) as candidate,
        neo4j.GraphDatabase.driver(
            settings["PLANT_PRODUCTION_URI"], auth=auth, max_transaction_retry_time=5
        ) as production,
        httpx.Client(base_url=settings["PLANT_ASSISTANT_URL"], timeout=120) as assistant,
        httpx.Client(base_url=tracking_uri, timeout=5) as stetiq_http,
    ):
        client = stetiq.Client(
            tracking_uri, token=settings["STETIQ_TOKEN"], graph_source=Neo4jGraphSource(candidate)
        )
        graphs = Graphs(candidate, production)
        check = stack_check(stetiq=stetiq_http, graphs=graphs, assistant=assistant)
        try:
            if args.reset:
                show = Show(
                    client,
                    graphs,
                    extraction=mode,
                    quiet=False,
                    rewind_tracking=rewind,
                    assistant=assistant,
                    check=check,
                )
                show.ready(0)
                show.rewind(guard="on")
                print("Rewound: stetiq, both graphs and the assistant are back at the start")
                return 0
            run_show(
                client,
                graphs,
                rewind_tracking=rewind,
                extraction=mode,
                assistant=assistant,
                start_act=args.act,
                check=check,
                pause=pause,
            )
            if args.epilogue:
                observer = stetiq.Client(
                    tracking_uri,
                    token=settings["STETIQ_TOKEN"],
                    graph_source=Neo4jGraphSource(production),
                )
                run_epilogue(observer, production, pause=pause)
        except StackDown as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except (
            stetiq.StetiqError,
            ExtractionError,
            AssistantError,
            RewindError,
            httpx.HTTPError,
            neo4j.exceptions.DriverError,
            neo4j.exceptions.Neo4jError,
        ) as e:
            # A container that went down mid-act: name it rather than the error it caused.
            down = check()
            print(f"error: {StackDown(down, args.act) if down else e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
