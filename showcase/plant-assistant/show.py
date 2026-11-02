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

It runs against the compose stack (docker-compose.yml): the stetiq server
(`STETIQ_TRACKING_URI`), two Neo4j servers, the candidate graph every Construction Run
builds (`PLANT_CANDIDATE_URI`) and the production graph a promoted run is deployed to
(`PLANT_PRODUCTION_URI`), with `NEO4J_USER` / `NEO4J_PASSWORD`, and the maintenance
assistant (`PLANT_ASSISTANT_URL`), which the show asks the scripted questions over its
HTTP API. Each one not set comes from the host ports and password in `.env`.
README.md tells how to run it on stage; STORY.md tells the story and its running order.

The show is played twice from the start: once without stetiq (Acts 0 and 1), then, after
a rewind, with it (Acts 0, 2 and 3). The rewind starts stetiq over on a new, empty data
volume, through docker compose; compose issues new API tokens with stetiq's CLI, and the
assistant restarts to read its own. It also empties both graphs, and resets the
assistant, with its Connector guard off for the first pass and on for the second.
`--act N` rewinds and replays the acts before N, so it starts Act N from the state they
leave.

Act 0, Monday morning: prompt v1 builds v1, the Gates pass, `production` is promoted
to v1 and the run is deployed. The assistant, on v1, answers both scripted questions.

Act 1, without stetiq: the assistant's guard is off, and the pipeline's CD deploys every
run its tests pass. Prompt v2 with Line 2's EAM export is deployed straight to the
production graph; the assistant follows it to v2, answers the suppliers question, and
says Line 2 had no breakdowns: its Cypher filters `kind = 'breakdown'`, and the EAM
export calls Line 2's two breakdowns `corrective`.

Act 2, with stetiq (after the rewind): prompt v2 with Line 2's EAM export passes every
Gate but fails the maintenance assistant's and the reliability dashboard's Consumer
Gates, so it stays the Candidate, unpromoted and undeployed. The assistant's Connector
guard refuses v2, naming the symptom, and the assistant stays on v1 and right.

Act 3, the fix: `WorkOrder.kind` bound to the `WorkOrderKind` Vocabulary passes the Gates
and the Consumer Gates; `production` moves to it and the run is deployed. The guard
accepts v3 on its next poll, and both scripted questions answer on it.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

SHOWCASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SHOWCASE_DIR))

import httpx  # noqa: E402
import neo4j  # noqa: E402
import neo4j.exceptions  # noqa: E402
from plant_assistant.assistant import KG, Guard, failing_findings  # noqa: E402
from plant_assistant.deploy import PRODUCTION_DATABASE, Graphs, deploy  # noqa: E402
from plant_assistant.epilogue import run_epilogue  # noqa: E402
from plant_assistant.evaluators import Documented, ReportCoverage  # noqa: E402
from plant_assistant.graph import Extraction  # noqa: E402
from plant_assistant.pipeline import (  # noqa: E402
    ExtractionError,
    LlmMode,
    Round,
    run_round,
)
from plant_assistant.stage import (  # noqa: E402
    RewindError,
    StackDown,
    compose_rewind,
    naming_down,
    presenter_pause,
    show_client,
    stack_check,
    stage_settings,
)

import stetiq  # noqa: E402
from stetiq import CompetencyQuestion, GraphSourceScope  # noqa: E402

__all__ = [
    "Graphs",
    "Show",
    "ShowState",
    "StackDown",
    "presenter_pause",
    "run_epilogue",
    "run_show",
    "stack_check",
]

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
class Answer:
    """The assistant's answer to a question, as its HTTP API returned it."""

    question: str
    answer: str
    cypher: str
    work_orders: list[str]
    ontology_version: int
    source: str  # live (Claude) | scripted (hand-written, offline)


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
    """The show's acts. `client` is None until the first rewind returns one."""

    def __init__(
        self,
        graphs: Graphs,
        *,
        rewind: Callable[[], stetiq.Client],
        extraction: LlmMode,
        quiet: bool,
        assistant: httpx.Client | None = None,
        check: Callable[[], list[str]] | None = None,
        pause: Callable[[str], None] | None = None,
    ) -> None:
        self.graphs = graphs
        self._rewind = rewind
        self.assistant = assistant
        self.check = check
        self.pause = pause
        self.extraction: LlmMode = extraction
        self.quiet = quiet
        self.state = ShowState()
        self._client: stetiq.Client | None = None

    @property
    def client(self) -> stetiq.Client:
        """The client of the stetiq server the last rewind started over."""
        if self._client is None:
            raise RuntimeError("the show has not rewound stetiq yet")
        return self._client

    def say(self, *lines: str, quiet: bool) -> None:
        if lines and not quiet:
            print(*lines, sep="\n", flush=True)

    def beat(self, label: str, *, quiet: bool) -> None:
        """A beat the audience sees: the presenter talks, then presses Enter. A quiet
        replay has none."""
        if self.pause is not None and not quiet:
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
        client.register_evaluator(Documented())
        client.register_evaluator(ReportCoverage())
        client.create_knowledge_graph(KG, ontology=ONTOLOGY / "v1.yaml")
        client.set_knowledge_graph_description(KG, DESCRIPTION)
        client.bind_graph_source(KG, GraphSourceScope(database=CANDIDATE_DATABASE))
        client.register_use_case(KG, USE_CASE)

    def rewind(self, *, guard: Guard) -> None:
        """Back to the start: stetiq started over (`rewind` returns the client of the new
        server), both graphs emptied, the assistant reset with its Connector guard
        `guard`, and the Knowledge Graph declared again."""
        self._client = self._rewind()
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
        self.ready(start_act)
        if start_act <= 1:
            self.rewind(guard="off")
            monday = self.play_act(0, self.act_0, quiet=self.quiet or start_act > 0)
            self.state.without_stetiq = [monday, self.play_act(1, self.act_1, quiet=self.quiet)]
            self.beat(REWIND, quiet=self.quiet)
            self.say("", REWIND, quiet=self.quiet)
            self.ready(2)
        self.rewind(guard="on")
        for number, act in ((0, self.act_0), (2, self.act_2), (3, self.act_3)):
            # Before `start_act`, an act replays without a word: the show starts after it.
            # Act 0 after the rewind always does: the audience saw it in the first pass.
            self.play_act(number, act, quiet=self.quiet or number == 0 or number < start_act)
        return self.state

    def play_act(self, number: int, act: Callable[[bool], ActState], *, quiet: bool) -> ActState:
        """`act`, once every container is up, after its beat. A container that goes
        down during the act is named, not the error it caused."""
        self.ready(number)
        self.beat(ACT_TITLES[number], quiet=quiet)
        with naming_down(self.check, number):
            return act(quiet)

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

    def act_0(self, quiet: bool) -> ActState:
        """Monday morning: prompt v1 builds v1, the Gates pass, `production` is promoted
        to v1, and the run is deployed. No Consumer Gate: this is the baseline."""
        act = self.gate(0, "v1", self.construct("v1"), consumers=False)
        self.say("", ACT_TITLES[0], act.line, *_detail_lines(act), quiet=quiet)
        return self.consult_assistant(act, quiet=quiet)

    def act_1(self, quiet: bool) -> ActState:
        """Without stetiq: the guard is off, and the pipeline's CD deploys every run its
        tests pass. Prompt v2 with Line 2's EAM export goes straight to the production
        graph, and the assistant follows it. The Use Case is the one Act 2's pull
        request meets, suppliers question and all: only stetiq's part is missing."""
        self.declare_parts_suppliers()
        run = self.construct("v2")
        tested = run.status == "finished"
        if tested:
            self.deploy(run)
        line = "   ".join(
            [ROUND_LABEL["v2"], f"tests {_mark(tested)}", *(["deployed"] if tested else [])]
        )
        self.say("", ACT_TITLES[1], line, quiet=quiet)
        act = ActState(
            1, "v2", line, run, None, False, tested, production_run=self.state.production_run
        )
        return self.consult_assistant(act, quiet=quiet)

    def act_2(self, quiet: bool) -> ActState:
        """With stetiq: the same pull request (prompt v2 and Line 2's EAM export) runs
        again, and its CI asks stetiq. Every Gate passes; the Consumer Gates fail, so
        the Candidate stays unpromoted and the production graph is not touched. The
        assistant's Connector guard refuses v2 and stays on v1."""
        self.declare_parts_suppliers()
        act = self.gate(2, "v2", self.construct("v2"))
        self.say("", ACT_TITLES[2], act.line, *_detail_lines(act), quiet=quiet)
        return self.consult_assistant(act, quiet=quiet)

    def act_3(self, quiet: bool) -> ActState:
        """The fix: v1 plus what prompt v2 added, with `WorkOrder.kind` bound to the
        `WorkOrderKind` Vocabulary, registered as the next Ontology Version. Prompt v2
        runs on it; the Gates and the Consumer Gates pass, `production` moves to it and
        the run is deployed. The assistant's Connector guard accepts v3 on its next
        poll."""
        fix = self.client.register_ontology(KG, ONTOLOGY / "fix.yaml")
        act = self.gate(3, "fix", self.construct("fix", ontology_version=fix.number))
        self.say("", ACT_TITLES[3], act.line, *_detail_lines(act), quiet=quiet)
        return self.consult_assistant(act, quiet=quiet)

    def consult_assistant(self, act: ActState, *, quiet: bool) -> ActState:
        """Record `act`, with what the assistant shows after it: over its HTTP API only,
        ask it to check stetiq now (one poll of its Connector guard), then read its
        status and ask it the scripted questions."""
        if self.assistant is not None:
            status = _json(self.assistant.post("/api/poll"))
            self.say(f"  assistant: {status['banner']}", quiet=quiet)
            answers: dict[str, Answer] = {}
            for question in SCRIPTED_QUESTIONS:
                self.beat(f"ask: {question}", quiet=quiet)
                reply = _json(self.assistant.post("/api/ask", json={"question": question}))
                answers[question] = Answer(**reply)
                self.say(f"  Q: {question}", f"  A: {reply['answer']}", quiet=quiet)
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

    def deploy(self, run: stetiq.ConstructionRun) -> None:
        """The pipeline's CD: the production graph now holds `run`."""
        deploy(self.graphs.production, self.state.extractions[run.id])
        self.state.production_run = run.id

    def gate(
        self, act_number: int, round_: Round, run: stetiq.ConstructionRun, *, consumers: bool = True
    ) -> ActState:
        """The pipeline's CI with stetiq: the Gates and (with `consumers`) every Consumer
        Gate on the run; `production` is promoted, and the run deployed, only when all
        of them pass."""
        if run.candidate_version is not None:
            # The custom Ontology Version Evaluator (`documented`) on the new Candidate;
            # the built-ins ran when stetiq proposed it.
            self.client.evaluate(KG, run.candidate_version)
        gates = self.client.evaluate_gates(KG, CONFIG, run=run.id)
        consumer_gates = (
            tuple(
                sorted(
                    self.client.evaluate_consumer_gates(KG, run=run.id), key=lambda c: c.consumer
                )
            )
            if consumers
            else ()
        )
        promoted = gates.passed and all(c.passed for c in consumer_gates)
        if promoted:
            self.client.set_alias(KG, "production", gates.ontology_version)
            self.deploy(run)
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
                f"{c.consumer} ❌ " + ", ".join(failing_findings(c, row_counts=True))
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


def run_show(
    graphs: Graphs,
    *,
    rewind: Callable[[], stetiq.Client],
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

    `rewind` starts the stetiq server over, empty, and returns a client of it that
    observes the candidate graph (its Graph Source must be `graphs.candidate`, e.g.
    `Neo4jGraphSource(graphs.candidate)`). On stage it is `compose_rewind(...)`; it must
    also give the assistant its new token. Each rewind then empties both graphs and
    resets the assistant. The show rewinds before its first act, so it needs no client
    of its own. `extraction` is how Claude's extraction runs: `replay` (the committed
    llm-cache/ only; a miss is an error), `live` (Claude on a miss) or `record` (Claude
    for every report).

    `assistant` is an HTTP client on the maintenance assistant's base URL (an
    `httpx.Client(base_url=...)`, or a FastAPI TestClient over its app); after an act
    the show reads its banner and asks it the scripted questions, over its HTTP API
    only.

    `check` (e.g. `stack_check(...)`) runs before the show and before each act; when it
    names a container that is down, the show stops with `StackDown`. `pause` is called
    at each beat the audience sees (e.g. `presenter_pause(...)`), never in a quiet
    replay."""
    show = Show(
        graphs,
        rewind=rewind,
        extraction=extraction,
        quiet=quiet,
        assistant=assistant,
        check=check,
        pause=pause,
    )
    return show.play(start_act)


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
        graphs = Graphs(candidate, production)
        check = stack_check(stetiq=stetiq_http, graphs=graphs, assistant=assistant)
        show = Show(
            graphs,
            rewind=compose_rewind(tracking_uri, candidate),
            extraction=mode,
            quiet=False,
            assistant=assistant,
            check=check,
            pause=pause,
        )
        try:
            with naming_down(check, args.act):
                if args.reset:
                    show.ready(0)
                    show.rewind(guard="on")
                    print("Rewound: stetiq, both graphs and the assistant are back at the start")
                    return 0
                show.play(args.act)
                if args.epilogue:
                    run_epilogue(show_client(tracking_uri, production), production, pause=pause)
        except (
            StackDown,
            stetiq.StetiqError,
            ExtractionError,
            AssistantError,
            RewindError,
            httpx.HTTPError,
            neo4j.exceptions.DriverError,
            neo4j.exceptions.Neo4jError,
        ) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
