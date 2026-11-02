"""The plant-assistant show: a GraphRAG Consumer that stetiq keeps honest.

    cd showcase/plant-assistant
    uv run python show.py              # replays the recorded Claude extraction rounds
    uv run python show.py --live       # calls Claude (the `claude` CLI) on a cache miss

stetiq is a remote server (`STETIQ_TRACKING_URI`, an API token in `STETIQ_TOKEN`); the
pipeline writes two Neo4j servers, the candidate graph every Construction Run builds
(`PLANT_CANDIDATE_URI`) and the production graph a promoted run is deployed to
(`PLANT_PRODUCTION_URI`), with `NEO4J_USER` / `NEO4J_PASSWORD`. STORY.md tells the
story and its running order.

Act 0, Monday morning: prompt v1 builds v1, the Gates pass, `production` is promoted
to v1 and the run is deployed.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

SHOWCASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SHOWCASE_DIR))

import neo4j  # noqa: E402
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
from stetiq import GraphSourceScope  # noqa: E402
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


@dataclass(frozen=True)
class Graphs:
    """The two Neo4j servers the pipeline writes: `candidate`, which every Construction
    Run rebuilds and stetiq observes, and `production`, which a deploy replays a
    promoted run into."""

    candidate: neo4j.Driver
    production: neo4j.Driver


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


@dataclass
class ShowState:
    """The state the show builds up, act by act (the test reads it back)."""

    acts: dict[int, ActState] = field(default_factory=dict)
    # Every run's Extraction, by run id: what a deploy replays into production.
    extractions: dict[str, Extraction] = field(default_factory=dict)

    @property
    def lines(self) -> list[str]:
        return [a.line for a in self.acts.values()]


class Show:
    def __init__(
        self, client: stetiq.Client, graphs: Graphs, *, extraction: LlmMode, quiet: bool
    ) -> None:
        self.client = client
        self.graphs = graphs
        self.extraction: LlmMode = extraction
        self.quiet = quiet
        self.state = ShowState()

    def say(self, *lines: str) -> None:
        if not self.quiet:
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
        parts = [ROUND_LABEL["v1"], f"Gate {_mark(gates.passed)}"]
        if promoted:
            parts += [f"promoted: production -> v{gates.ontology_version}", "deployed"]
        act = ActState(0, "v1", "   ".join(parts), run, gates, promoted, promoted)
        self.state.acts[0] = act
        self.say("Act 0, Monday morning", act.line)
        for o in gates.outcomes:
            if not o.passed:
                self.say(f"    Gate {o.gate.name} failed: {'; '.join(o.reasons[:3])}")
        return act


def _mark(passed: bool) -> str:
    return "✅" if passed else "❌"


def run_show(
    client: stetiq.Client,
    graphs: Graphs,
    *,
    extraction: LlmMode = "replay",
    quiet: bool = False,
) -> ShowState:
    """Run the show headless from an empty stetiq and empty graphs.

    `client` reaches the stetiq server and observes the candidate graph: its Graph Source
    must be `graphs.candidate` (e.g. `Neo4jGraphSource(graphs.candidate)`). `extraction`
    is how Claude's extraction runs: `replay` (the committed llm-cache/ only; a miss is
    an error), `live` (Claude on a miss) or `record` (Claude for every report)."""
    show = Show(client, graphs, extraction=extraction, quiet=quiet)
    show.declare()
    show.act_0()
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
    ):
        client = stetiq.Client(graph_source=Neo4jGraphSource(candidate))
        try:
            run_show(client, Graphs(candidate, production), extraction=mode)
        except (stetiq.StetiqError, ExtractionError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
