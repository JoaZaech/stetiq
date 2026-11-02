"""The plant-assistant show: a GraphRAG Consumer that stetiq keeps honest.

    cd showcase/plant-assistant
    uv run python show.py              # replays the recorded Claude extraction rounds
    uv run python show.py --live       # calls Claude (the `claude` CLI) on a cache miss

stetiq is a remote server (`STETIQ_TRACKING_URI`, an API token in `STETIQ_TOKEN`); the
pipeline writes two Neo4j servers, the candidate graph every Construction Run builds
(`PLANT_CANDIDATE_URI`) and the production graph a promoted run is deployed to
(`PLANT_PRODUCTION_URI`), with `NEO4J_USER` / `NEO4J_PASSWORD`. The maintenance
assistant runs at `PLANT_ASSISTANT_URL`; the show asks it the scripted questions over
its HTTP API. STORY.md tells the story and its running order.

Act 0, Monday morning: prompt v1 builds v1, the Gates pass, `production` is promoted
to v1 and the run is deployed. The assistant, on v1, answers both scripted questions.

Act 2, with stetiq: prompt v2 with Line 2's EAM export passes every Gate but fails the
maintenance assistant's and the reliability dashboard's Consumer Gates, so it stays the
Candidate, unpromoted and undeployed. The assistant's Connector guard refuses v2, naming
the symptom, and the assistant stays on v1 and right.

Act 3, the fix: `WorkOrder.kind` bound to the `WorkOrderKind` Vocabulary passes the Gates
and the Consumer Gates; `production` moves to it and the run is deployed. The guard
accepts v3 on its next poll, and both scripted questions answer on it.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHOWCASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SHOWCASE_DIR))

from dataclasses import replace  # noqa: E402

import httpx  # noqa: E402
import neo4j  # noqa: E402
from plant_assistant.assistant import percent  # noqa: E402
from plant_assistant.deploy import deploy  # noqa: E402
from plant_assistant.evaluators import Documented, ReportCoverage  # noqa: E402
from plant_assistant.graph import Extraction  # noqa: E402
from plant_assistant.pipeline import (  # noqa: E402
    ExtractionError,
    LlmMode,
    Round,
    run_round,
)

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
    gates: stetiq.GateResult
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

    acts: dict[int, ActState] = field(default_factory=dict)
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
        assistant: httpx.Client | None = None,
    ) -> None:
        self.client = client
        self.graphs = graphs
        self.assistant = assistant
        self.extraction: LlmMode = extraction
        self.quiet = quiet
        self.state = ShowState()

    def say(self, *lines: str) -> None:
        if lines and not self.quiet:
            print(*lines, sep="\n", flush=True)

    def declare(self) -> None:
        """The Knowledge Graph, its v1 Ontology, its Use Case, and its Graph Source scope
        bound to the candidate graph. The pipeline's Evaluators are registered first, so
        `documented` judges v1 too."""
        client = self.client
        client.register_evaluator(Documented())
        client.register_evaluator(ReportCoverage())
        client.create_knowledge_graph(KG, ontology=ONTOLOGY / "v1.yaml")
        client.set_knowledge_graph_description(KG, DESCRIPTION)
        client.bind_graph_source(KG, GraphSourceScope(database=CANDIDATE_DATABASE))
        client.register_use_case(KG, USE_CASE)

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
        self.say("Act 0, Monday morning", line)
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

    def consult_assistant(self, act: ActState) -> ActState:
        """Record `act`, with what the assistant shows after it: over its HTTP API only,
        ask it to check stetiq now (one poll of its Connector guard), then read its
        status and ask it the scripted questions."""
        if self.assistant is not None:
            status = _json(self.assistant.post("/api/poll"))
            self.say(f"  assistant: {status['banner']}")
            answers: dict[str, Answer] = {}
            for question in SCRIPTED_QUESTIONS:
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
        self.say("Act 2, with stetiq", act.line)
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
        self.say("Act 3, the fix", act.line)
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
    for o in act.gates.outcomes:
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


def run_show(
    client: stetiq.Client,
    graphs: Graphs,
    *,
    extraction: LlmMode = "replay",
    quiet: bool = False,
    assistant: httpx.Client | None = None,
) -> ShowState:
    """Run the show headless from an empty stetiq and empty graphs.

    `client` reaches the stetiq server and observes the candidate graph: its Graph Source
    must be `graphs.candidate` (e.g. `Neo4jGraphSource(graphs.candidate)`). `extraction`
    is how Claude's extraction runs: `replay` (the committed llm-cache/ only; a miss is
    an error), `live` (Claude on a miss) or `record` (Claude for every report).

    `assistant` is an HTTP client on the maintenance assistant's base URL (an
    `httpx.Client(base_url=...)`, or a FastAPI TestClient over its app); after an act
    the show reads its banner and asks it the scripted questions, over its HTTP API
    only."""
    show = Show(client, graphs, extraction=extraction, quiet=quiet, assistant=assistant)
    show.declare()
    show.act_0()
    show.act_2()
    show.act_3()
    return show.state


def _driver(uri_env: str, default: str) -> neo4j.Driver:
    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    return neo4j.GraphDatabase.driver(os.environ.get(uri_env, default), auth=auth)


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
    args = parser.parse_args(argv)
    mode: LlmMode = "record" if args.record else "live" if args.live else "replay"
    with (
        _driver("PLANT_CANDIDATE_URI", "bolt://localhost:7687") as candidate,
        _driver("PLANT_PRODUCTION_URI", "bolt://localhost:7688") as production,
        httpx.Client(
            base_url=os.environ.get("PLANT_ASSISTANT_URL", "http://localhost:8000"), timeout=120
        ) as assistant,
    ):
        client = stetiq.Client(graph_source=Neo4jGraphSource(candidate))
        try:
            run_show(client, Graphs(candidate, production), extraction=mode, assistant=assistant)
        except (stetiq.StetiqError, ExtractionError, AssistantError, httpx.HTTPError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
