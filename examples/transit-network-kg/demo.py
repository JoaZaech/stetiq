"""Drive stetiq from the command line on the city-transit Knowledge Graph, the way a
platform team's CI pipeline would.

    cd examples/transit-network-kg
    uv run python demo.py            # the walkthrough: every act is a `stetiq` command
    uv run stetiq ui                 # then browse the result

Each act invokes the stetiq CLI in-process (typer's CliRunner on `stetiq.cli.app`),
records the exit code and the output, and prints the equivalent shell command line, so
README.md can show a real transcript. The exit codes are the contract a CI job scripts
against: 0 success, 1 error (a run that did not finish, a bad config file), 3 a finding
(a failed Gate, Drift).

Everything is local: the tracking database is .stetiq/stetiq.db, the graph database is
the file .graphdb/transit.json (see transit_graph.py), the feeds are in data/.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
import shlex
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
if str(EXAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_DIR))

from transit_graph import DEFAULT_DATABASE, TransitGraph  # noqa: E402
from transit_pipeline import DATA_DIR, DEFAULT_GRAPH_FILE  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

import stetiq.client  # noqa: E402
from stetiq.cli import app  # noqa: E402

KG = "city-transit"
CONFIG = EXAMPLE_DIR / "stetiq.yaml"
BROKEN_CONFIG = EXAMPLE_DIR / "gates-broken.yaml"
ONTOLOGY = EXAMPLE_DIR / "ontology"
USE_CASE = EXAMPLE_DIR / "use-case.yaml"
FEED_JUNE = DATA_DIR / "gtfs"
FEED_SEPTEMBER = DATA_DIR / "gtfs-2026-09"
DEFAULT_TRACKING_URI = f"sqlite:///{EXAMPLE_DIR / '.stetiq' / 'stetiq.db'}"
HAND_EDIT_SEED = (
    2026  # which StopTime nodes the hand edit deletes: fixed, so the test can pin counts
)

DESCRIPTION = (
    "Lindenhaven Transit's timetable as a graph: GTFS **routes**, **trips**, **stops** and "
    "**stop times**, plus the **depots** and **fare zones** from the operator's other systems. "
    "Built by `transit_pipeline.py` through `stetiq run`."
)

RUN_LINE = re.compile(r"Construction Run (\w+) (\w+) \(Ontology Version (\d+)\)")
GATE_LINE = re.compile(r"^(PASS|FAIL)  (\S+)", re.MULTILINE)
FINDING_LINE = re.compile(r"^  (\w+)\s+(\w+)\s+(\S+)", re.MULTILINE)
METRIC = re.compile(r"(\w+)=([\d.]+)")


@dataclass
class Step:
    """One CLI invocation: what a CI log would show, plus the exit code it would act on."""

    name: str
    command: str  # the shell form, relative to the example folder
    exit_code: int
    output: str

    @property
    def lines(self) -> list[str]:
        return self.output.splitlines()

    def metrics(self, evaluator: str) -> dict[str, float]:
        """The `name=value` pairs on the line `stetiq ontology evaluate` prints for `evaluator`."""
        line = next(line for line in self.lines if line.startswith(f"{evaluator}"))
        return {k: float(v) for k, v in METRIC.findall(line.split(":", 1)[1])}

    def gates(self) -> dict[str, bool]:
        return {name: verdict == "PASS" for verdict, name in GATE_LINE.findall(self.output)}

    def findings(self) -> list[tuple[str, str, str]]:
        """(kind, subject kind, subject) per Drift finding `stetiq observe` listed."""
        return [tuple(m) for m in FINDING_LINE.findall(self.output)]  # type: ignore[misc]

    @property
    def run_id(self) -> str:
        return RUN_LINE.search(self.output).group(1)  # type: ignore[union-attr]


@dataclass
class Demo:
    """The state the walkthrough builds up (the test reads it back): every step by name."""

    tracking_uri: str
    graph_file: Path
    quiet: bool
    steps: dict[str, Step] = field(default_factory=dict)
    runs: dict[str, str] = field(default_factory=dict)  # run name -> Construction Run id
    stop_times_deleted: int = 0

    def __post_init__(self) -> None:
        self.graph = TransitGraph(self.graph_file)
        self.runner = CliRunner()
        self.partial_feed = self.graph_file.parent / "gtfs-2026-09-partial"

    # --- output -----------------------------------------------------------------------

    def say(self, *lines: str) -> None:
        if not self.quiet:
            print(*lines, sep="\n", flush=True)

    def act(self, title: str) -> None:
        self.say("", f"=== {title} ", "")

    def step(self, name: str) -> Step:
        return self.steps[name]

    # --- the CLI ----------------------------------------------------------------------

    def stetiq(self, name: str, *args: str, env: dict[str, str] | None = None) -> Step:
        """Run `stetiq <args>` in-process against the tracking database and record it.

        `env` is set for the duration of the command, the way a CI step sets it: the
        pipeline's own settings (TRANSIT_FEED_DIR) and PYTHONPATH for custom Evaluators."""
        shown_env = " ".join(f"{k}={shlex.quote(_relative(v))}" for k, v in (env or {}).items())
        shown = shlex.join(_relative(a) for a in args)
        self.say(f"$ {shown_env}{' ' if shown_env else ''}stetiq {shown}")
        with _environment(env or {}):
            result = self.runner.invoke(app, [*args, "--tracking-uri", self.tracking_uri])
        output = result.output.rstrip("\n")
        if result.exception and not isinstance(result.exception, SystemExit):
            raise result.exception
        step = Step(name, f"stetiq {shown}", result.exit_code, output)
        self.steps[name] = step
        self.say(*(f"  {line}" for line in step.lines), f"  [exit {step.exit_code}]", "")
        return step

    def run(self, name: str, *args: str, env: dict[str, str] | None = None) -> Step:
        """`stetiq run`: the Construction Entry Point of stetiq.yaml as a Construction Run."""
        step = self.stetiq(name, "run", "--config", str(CONFIG), *args, env=env)
        self.runs[name] = step.run_id
        return step

    # --- 1. declare -------------------------------------------------------------------

    def declare(self) -> None:
        self.act("1. Declare: the Knowledge Graph, its Graph Source, its Use Case, strict mode")
        self.stetiq("kg-create", "kg", "create", KG, "--ontology", str(ONTOLOGY / "v1.yaml"))
        self.stetiq("kg-description", "kg", "description", KG, DESCRIPTION)
        self.stetiq("bind-source", "kg", "bind-source", KG, "--database", DEFAULT_DATABASE)
        self.stetiq("use-case-register", "use-case", "register", KG, str(USE_CASE))
        self.stetiq("evaluations-v1", "ontology", "evaluations", KG, "1")
        self.stetiq("evolution-strict", "kg", "evolution-mode", KG, "strict")

    # --- 2. build ---------------------------------------------------------------------

    def build(self) -> None:
        self.act("2. Build: strict mode fails the run, evolving mode yields a Candidate")
        self.say(
            "The June feed carries wheelchairBoarding, bikesAllowed and parent_station; v1 declares none of them."
        )
        self.run("run-strict")
        self.stetiq("runs-list-after-strict", "runs", "list", KG)
        self.stetiq("runs-get-strict", "runs", "get", self.runs["run-strict"])
        self.stetiq("evolution-evolving", "kg", "evolution-mode", KG, "evolving")
        self.run("run-evolving")
        self.stetiq("diff-1-2", "ontology", "diff", KG, "1", "2")
        self.say("The Candidate spells the new Concepts the way the feed does. The platform team's")
        self.say(
            "naming_conventions Evaluator runs in the CLI process and records its result on v2:"
        )
        evaluator = ("--evaluator", "transit_evaluators:NamingConventions")
        pythonpath = {"PYTHONPATH": str(EXAMPLE_DIR)}
        self.stetiq("evaluate-v2", "ontology", "evaluate", KG, "2", *evaluator, env=pythonpath)
        self.say(
            "A human writes ontology/v3.yaml: the same Concepts under proper names, documented."
        )
        self.stetiq("register-v3", "ontology", "register", KG, str(ONTOLOGY / "v3.yaml"))
        self.stetiq("evaluate-v3", "ontology", "evaluate", KG, "3", *evaluator, env=pythonpath)
        self.stetiq("diff-1-3", "ontology", "diff", KG, "1", "3")

    # --- 3. gate and promote ----------------------------------------------------------

    def gate_and_promote(self) -> None:
        self.act("3. Gate: a run consumes v3, the Gates pass, CI promotes production")
        self.stetiq("gate-v2", "gate", KG, "--version", "2", "--config", str(CONFIG))
        self.run("run-v3", "--ontology-version", "3")
        self.stetiq("gate-v3", "gate", KG, "--version", "3", "--config", str(CONFIG))
        if self.step("gate-v3").exit_code == 0:
            self.stetiq(
                "alias-set-production", "alias", "set", KG, "production", "3", "--actor", "ci-bot"
            )
        self.stetiq("alias-log", "alias", "log", KG)

    # --- 4. operate -------------------------------------------------------------------

    def operate(self) -> None:
        self.act("4. Operate: a new feed, a bad export, a hand edit")
        self.stetiq("observe-clean", "observe", "--config", str(CONFIG))
        self.say(
            "September: the planning tool publishes data/gtfs-2026-09 (night line N1 withdrawn,"
        )
        self.say("North Depot renamed). The nightly rebuild points the pipeline at it:")
        september = {"TRANSIT_FEED_DIR": str(FEED_SEPTEMBER)}
        self.run("run-september", env=september)
        self.stetiq(
            "gate-run-september",
            "gate",
            KG,
            "--run",
            self.runs["run-september"],
            "--config",
            str(CONFIG),
        )
        self.say(
            "The next export is cut short: calendar.txt lost the weekend service. The structure"
        )
        self.say("is intact (Conformance 1.0), only the counts give it away:")
        _write_partial_feed(FEED_SEPTEMBER, self.partial_feed)
        self.run("run-partial", env={"TRANSIT_FEED_DIR": str(self.partial_feed)})
        self.stetiq(
            "gate-run-partial",
            "gate",
            KG,
            "--run",
            self.runs["run-partial"],
            "--config",
            str(CONFIG),
        )
        self.stop_times_deleted = self._hand_edit()
        self.say(
            f"Someone deletes {self.stop_times_deleted} StopTime nodes straight in the database (40%)."
        )
        self.stetiq("observe-after-hand-edit", "observe", "--config", str(CONFIG))
        self.stetiq("drift-list", "drift", "list", KG)

    def _hand_edit(self) -> int:
        """Delete 40% of the StopTime nodes directly in the graph database, outside any run."""
        self.graph.load()
        stop_times = sorted(n.id for n in self.graph.nodes("StopTime", DEFAULT_DATABASE))
        doomed = random.Random(HAND_EDIT_SEED).sample(stop_times, k=int(len(stop_times) * 0.4))
        deleted = self.graph.delete_nodes(doomed)
        self.graph.save()
        return deleted

    # --- 5. a config error, then compare ----------------------------------------------

    def finish(self) -> None:
        self.act("5. A broken config exits 1, not 3; compare the runs; browse")
        self.stetiq(
            "gate-broken-config", "gate", KG, "--version", "3", "--config", str(BROKEN_CONFIG)
        )
        self.stetiq("runs-compare", "runs", "compare", *self.runs.values())
        self.stetiq("ontology-list", "ontology", "list", KG)
        here = EXAMPLE_DIR.resolve() == Path.cwd().resolve()
        self.say(
            "Browse the tracking database" + ("" if here else f" (from {EXAMPLE_DIR})") + ":",
            "  uv run stetiq ui                      # http://127.0.0.1:5000/ui",
            f"  uv run stetiq runs list {KG}",
            f"  uv run stetiq gate-results {KG}       # every Gate evaluation this story recorded",
            f"  uv run stetiq alias log {KG}",
            f"  uv run stetiq drift list {KG}",
        )


# --- helpers ---------------------------------------------------------------------------


def _relative(value: str) -> str:
    """Show paths relative to the example folder, as a shell transcript run from it would."""
    root = str(EXAMPLE_DIR)
    if value == root:
        return "."
    return value.removeprefix(root + os.sep)


@contextmanager
def _environment(values: dict[str, str]) -> Iterator[None]:
    """Set `values` for one command. A fresh `stetiq` process reads PYTHONPATH at start,
    so for the in-process CLI the same folders go on sys.path for the duration."""
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    added = [p for p in values.get("PYTHONPATH", "").split(os.pathsep) if p and p not in sys.path]
    sys.path[:0] = added
    try:
        yield
    finally:
        for p in added:
            sys.path.remove(p)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _write_partial_feed(source: Path, target: Path) -> None:
    """The September feed with calendar.txt cut to the weekday service: the exporter's
    bad night. Trips still reference WKE, so the pipeline writes them without RUNS_ON."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    with (source / "calendar.txt").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0])
    with (target / "calendar.txt").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(r for r in rows if r["service_id"] == "WKD")


def run_demo(
    *,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    graph_file: Path = DEFAULT_GRAPH_FILE,
    quiet: bool = False,
) -> Demo:
    demo = Demo(tracking_uri=tracking_uri, graph_file=Path(graph_file), quiet=quiet)
    demo.say(
        f"Transcript from {EXAMPLE_DIR}; every command also received --tracking-uri {tracking_uri}",
        f"Graph database: {demo.graph.path}",
    )
    # What the CLI needs from the environment, the way a CI job exports it: where the
    # pipeline writes (its own setting, not stetiq's) and which `python` the Entry Point
    # command in stetiq.yaml resolves to. The Graph Source adapter is the one piece a
    # real deployment configures with STETIQ_GRAPH_SOURCE_URI (Neo4j); stetiq knows no
    # file-backed store, so the demo hands the CLI this one the way stetiq's own CLI tests
    # do, for as long as the walkthrough runs.
    env = {
        "TRANSIT_GRAPH_FILE": str(demo.graph_file),
        "TRANSIT_FEED_DIR": str(FEED_JUNE),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    from_env = stetiq.client.graph_source_from_env
    stetiq.client.graph_source_from_env = lambda environ=None: demo.graph  # type: ignore[assignment]
    try:
        with _environment(env):
            demo.declare()
            demo.build()
            demo.gate_and_promote()
            demo.operate()
            demo.finish()
    finally:
        stetiq.client.graph_source_from_env = from_env
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tracking-uri", default=DEFAULT_TRACKING_URI)
    parser.add_argument("--graph-file", default=str(DEFAULT_GRAPH_FILE))
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the tracking database and the graph database file first",
    )
    args = parser.parse_args(argv)

    db = (
        Path(args.tracking_uri.removeprefix("sqlite:///"))
        if args.tracking_uri.startswith("sqlite:///")
        else None
    )
    graph_file = Path(args.graph_file)
    if args.reset:
        for path in (db, graph_file):
            if path is not None and path.exists():
                path.unlink()
    elif db is not None and db.exists():
        print(
            f"{db} already holds a previous walkthrough; pass --reset to start over",
            file=sys.stderr,
        )
        return 1
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_demo(tracking_uri=args.tracking_uri, graph_file=graph_file)
    except stetiq.StetiqError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
