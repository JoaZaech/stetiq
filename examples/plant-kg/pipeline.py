"""Builds the plant maintenance Knowledge Graph from the plant's own data.

Sources, under data/:

| Source                      | Kind         | Gives                                              |
| --------------------------- | ------------ | -------------------------------------------------- |
| assets/machines.csv         | structured   | Machine, Line, PART_OF                             |
| assets/material_flow.json   | structured   | FEEDS, as drawn in the layout (can be stale)       |
| cmms/work_orders.csv        | structured   | WorkOrder, PERFORMED_ON, ASSIGNED_TO, Technician   |
| hr/technicians.csv          | structured   | Technician.badge (rules-v2 and claude only)        |
| reports/*.txt, *.eml        | unstructured | Component, FollowUp, Fault, Supplier, FEEDS stated in prose |

The structured sources load deterministically. The technicians' reports go through an
extractor:

- `rules-v1`: the plant's original regex script. Reads the report header, the components
  and the follow-ups. Cannot read the email format and ignores causes and suppliers.
- `rules-v2`: the regex script after a fix round. Also reads root causes, replacement-part
  suppliers, material-flow statements, and the email format.
- `claude`: Claude, through the Claude Code CLI (`claude -p`), guided by the Declared
  Ontology stetiq hands the run. The default when `claude` is on PATH.

Every extractor returns the same shape (`Draft`: nodes keyed by (label, key), plus
relationships), so the writer and the rest of the pipeline do not care which produced it.

Run it as the Construction Entry Point (see stetiq.yaml):

    python pipeline.py --ontology declared.yaml --scope '{"database": "plant"}'

Environment: PLANT_GRAPH_FILE (where the local graph store lives), PLANT_EXTRACTOR
(`auto`, `rules-v1`, `rules-v2` or `claude`), PLANT_EXTRACTION_MODEL and PLANT_LLM_CACHE.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graphdb import DEFAULT_DATABASE, LocalGraph

from stetiq.ontology import Ontology, parse_yaml, to_yaml

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
DEFAULT_GRAPH_FILE = EXAMPLE_DIR / ".graphdb" / "plant.json"
DEFAULT_LLM_CACHE = EXAMPLE_DIR / ".graphdb" / "llm-cache"
DEFAULT_MODEL = "claude-opus-5-5"

# --- The shape every source produces ---------------------------------------------------

Key = tuple[str, str]  # (label, key)

# Which property holds a node's key. None: the key is synthetic and not written.
KEY_PROPERTY: dict[str, str | None] = {
    "Machine": "name",
    "Line": "name",
    "Component": "name",
    "Technician": "name",
    "WorkOrder": "id",
    "Supplier": "name",
    "FollowUp": None,
    "Fault": None,
}


@dataclass
class Draft:
    """Nodes and relationships one source contributes, merged by (label, key).

    The first value seen for a property wins, so the structured sources (loaded first)
    are never overwritten by what a report says."""

    nodes: dict[Key, dict[str, Any]] = field(default_factory=dict)
    relationships: list[tuple[Key, str, Key]] = field(default_factory=list)

    def node(self, label: str, key: str, **properties: Any) -> Key:
        props = self.nodes.setdefault((label, key), {})
        for name, value in properties.items():
            if value is not None and props.get(name) is None:
                props[name] = value
        return (label, key)

    def relate(self, start: Key, type_: str, end: Key) -> None:
        edge = (start, type_, end)
        if edge not in self.relationships:
            self.relationships.append(edge)

    def merge(self, other: Draft) -> None:
        for (label, key), props in other.nodes.items():
            self.node(label, key, **props)
        for start, type_, end in other.relationships:
            self.relate(start, type_, end)


# --- Structured sources ----------------------------------------------------------------


def load_structured(data_dir: Path = DATA_DIR, *, join_technicians: bool) -> Draft:
    draft = Draft()
    for row in _csv(data_dir / "assets" / "machines.csv"):
        machine = draft.node(
            "Machine", row["machine_id"], name=row["machine_id"], model=row["model"]
        )
        draft.relate(machine, "PART_OF", draft.node("Line", row["line"], name=row["line"]))
    flow = json.loads((data_dir / "assets" / "material_flow.json").read_text(encoding="utf-8"))
    for edge in flow["edges"]:
        draft.relate(
            draft.node("Machine", edge["from"]), "FEEDS", draft.node("Machine", edge["to"])
        )
    for row in _csv(data_dir / "cmms" / "work_orders.csv"):
        order = draft.node(
            "WorkOrder",
            row["work_order_id"],
            id=row["work_order_id"],
            title=row["title"],
            kind=row["kind"],
            opened_at=dt.date.fromisoformat(row["opened_at"]),
            # The CMMS export gained this column last quarter; initial.yaml does not declare it.
            downtime_minutes=int(row["downtime_minutes"]),
        )
        draft.relate(order, "PERFORMED_ON", draft.node("Machine", row["machine_id"]))
        draft.relate(order, "ASSIGNED_TO", draft.node("Technician", row["technician"]))
    if join_technicians:
        for row in _csv(data_dir / "hr" / "technicians.csv"):
            draft.node("Technician", row["name"], name=row["name"], badge=row["badge"])
    return draft


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# --- Unstructured reports --------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    name: str
    text: str


def read_reports(data_dir: Path = DATA_DIR) -> list[Report]:
    folder = data_dir / "reports"
    return [
        Report(p.name, p.read_text(encoding="utf-8"))
        for p in sorted(folder.iterdir())
        if p.suffix in (".txt", ".eml")
    ]


@dataclass(frozen=True)
class Context:
    """What the structured sources already know, handed to the extractors."""

    machines: tuple[str, ...]
    technicians: tuple[str, ...]


class Extractor:
    name: str
    joins_technicians: bool = False
    workers: int = 1

    def extract(self, report: Report, ontology: Ontology, context: Context) -> Draft | None:
        """The report's contribution, or None when the extractor cannot read it."""
        raise NotImplementedError

    def extract_all(
        self, reports: Sequence[Report], ontology: Ontology, context: Context
    ) -> list[Draft | None]:
        if self.workers <= 1:
            return [self.extract(r, ontology, context) for r in reports]
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(lambda r: self.extract(r, ontology, context), reports))


_FOLLOW_UP = re.compile(r"^- \[( |x)\] (.+?) \(owner: (.+?)\)\s*$", re.M)
_HEADER_V1 = re.compile(
    r"^(?P<id>WO-\d{4}) / (?P<machine>\S+) / (?P<date>[^/\n]+?) / "
    r"(?P<technician>[^(\n]+?)(?: \(badge (?P<badge>T-\d{3})\))?\s*$"
)
_INVOLVED_V1 = re.compile(r"The work involved (.+?)[.:]")
_WORK_ORDER_ID = re.compile(r"\bWO-\d{4}\b")
_BADGE = re.compile(r"([^\s/(][^/(\n]*?) \(badge (T-\d{3})\)")
_INVOLVED_V2 = re.compile(r"(?:The work involved|Work involved:) (.+?)[.:\n]")
_CAUSE_V2 = re.compile(r"[Rr]oot cause(?: was|:) (.+?)\.")
_SUPPLIER_V2 = re.compile(
    r"(?:A replacement (.+?) was ordered from|Replacement part: (.+?), ordered from) ([A-Z][\w&-]+)"
)
_FLOW_V2 = re.compile(
    r"\b([A-Z][A-Za-z]*-\d{2}) (?:feeds|supplies [a-z ]+? to) ([A-Z][A-Za-z]*-\d{2})\b"
)


def _components(text: str) -> list[str]:
    return [
        c.strip().removeprefix("the ").strip() for c in re.split(r", | and ", text) if c.strip()
    ]


def _follow_ups(draft: Draft, order: Key, text: str) -> None:
    for n, (done, description, owner) in enumerate(_FOLLOW_UP.findall(text), start=1):
        follow_up = draft.node(
            "FollowUp",
            f"{order[1]}#{n}",
            description=description,
            status="done" if done == "x" else "open",
        )
        draft.relate(order, "HAS_FOLLOW_UP", follow_up)
        draft.relate(follow_up, "ASSIGNED_TO", draft.node("Technician", owner, name=owner))


class RulesV1(Extractor):
    """The original regex script: header line, components and follow-ups only."""

    name = "rules-v1"

    def extract(self, report: Report, ontology: Ontology, context: Context) -> Draft | None:
        header = _HEADER_V1.match(report.text.splitlines()[0])
        if header is None:
            return None  # not the report format the script was written for
        draft = Draft()
        order = draft.node("WorkOrder", header["id"])
        draft.node("Technician", header["technician"].strip(), badge=header["badge"])
        if found := _INVOLVED_V1.search(report.text):
            for component in _components(found.group(1)):
                draft.relate(order, "INVOLVED", draft.node("Component", component))
        _follow_ups(draft, order, report.text)
        return draft


class RulesV2(Extractor):
    """The regex script after the fix round: causes, suppliers, flow statements, emails."""

    name = "rules-v2"
    joins_technicians = True

    def extract(self, report: Report, ontology: Ontology, context: Context) -> Draft | None:
        found_id = _WORK_ORDER_ID.search(report.text)
        if found_id is None:
            return None
        draft = Draft()
        order = draft.node("WorkOrder", found_id.group())
        for name, badge in _BADGE.findall(report.text):
            draft.node("Technician", name.strip(), badge=badge)
        if found := _INVOLVED_V2.search(report.text):
            for component in _components(found.group(1)):
                draft.relate(order, "INVOLVED", draft.node("Component", component))
        if found := _CAUSE_V2.search(report.text):
            draft.relate(
                order, "CAUSED_BY", draft.node("Fault", order[1], description=found.group(1))
            )
        for part_a, part_b, supplier in _SUPPLIER_V2.findall(report.text):
            component = draft.node("Component", part_a or part_b)
            draft.relate(component, "SUPPLIED_BY", draft.node("Supplier", supplier))
        for source, target in _FLOW_V2.findall(report.text):
            draft.relate(draft.node("Machine", source), "FEEDS", draft.node("Machine", target))
        _follow_ups(draft, order, report.text)
        return draft


class ExtractionError(Exception):
    """The Claude Code CLI could not produce an extraction."""


_PROMPT_VERSION = "1"
_SYSTEM_PROMPT = (
    "You are the extraction step of a knowledge-graph construction pipeline for a "
    "manufacturing plant. You read one maintenance report and return the nodes and "
    "relationships it states, as JSON matching the given schema. You never invent facts."
)
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "key": {"type": "string"},
                    "properties": {
                        "type": "object",
                        "additionalProperties": {"type": ["string", "number", "boolean"]},
                    },
                },
                "required": ["label", "key", "properties"],
                "additionalProperties": False,
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_label": {"type": "string"},
                    "start_key": {"type": "string"},
                    "type": {"type": "string"},
                    "end_label": {"type": "string"},
                    "end_key": {"type": "string"},
                },
                "required": ["start_label", "start_key", "type", "end_label", "end_key"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nodes", "relationships"],
    "additionalProperties": False,
}


class ClaudeExtractor(Extractor):
    """Extraction by Claude through the Claude Code CLI, guided by the Declared Ontology.

    Each report is one `claude -p` call with a JSON schema for the output, no tools and
    a replaced system prompt. Results are cached on disk by (prompt version, model,
    ontology, report), so a rebuild with the same inputs costs nothing.
    """

    name = "claude"
    joins_technicians = True
    workers = 4

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        cache_dir: Path = DEFAULT_LLM_CACHE,
        effort: str = "low",
    ) -> None:
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.effort = effort
        self.calls = 0
        self.cache_hits = 0

    def extract(self, report: Report, ontology: Ontology, context: Context) -> Draft | None:
        prompt = self._prompt(report, ontology, context)
        key = hashlib.sha256(f"{_PROMPT_VERSION}\n{self.model}\n{prompt}".encode()).hexdigest()
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            self.cache_hits += 1
            output = json.loads(cached.read_text(encoding="utf-8"))
        else:
            print(f"  extracting {report.name} with {self.model} ...", file=sys.stderr)
            output = self._call(prompt)
            self.calls += 1
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8")
        return self._to_draft(output)

    def _prompt(self, report: Report, ontology: Ontology, context: Context) -> str:
        order = _WORK_ORDER_ID.search(report.text)
        return f"""Extract the property graph stated by the maintenance report below.

## Declared Ontology (stetiq YAML)

{to_yaml(ontology)}
## Rules

- Use only the node labels, property names, relationship types and patterns the ontology declares, and leave out facts it has no place for. Relationship direction follows the patterns.
- Keys: Machine, the asset id as written (e.g. CNC-04). WorkOrder, its id (e.g. WO-2031). Technician, the full name. Component, the part name in lower case, singular, as written in the report (e.g. "spindle bearing"). Supplier, the vendor name. Fault, the work order id (one root cause per work order). FollowUp, "<work order id>#<n>", numbered from 1 in the order they appear.
- Property values follow the declared type: DATE as YYYY-MM-DD, INTEGER as a number, STRING as text. A FollowUp's status is "open" or "done".
- The work order, its machine, its technician and its date already come from the CMMS export: emit those nodes with their key only. Attach what the report adds: the components the work involved, the follow-ups with their owner, the root cause, the supplier a replacement component was ordered from, and material-flow statements between machines (one machine feeding or supplying parts to another).

## Context

Work order: {order.group() if order else "unknown"}
Known machines: {", ".join(context.machines)}
Known technicians: {", ".join(context.technicians)}

## Report ({report.name})

{report.text}"""

    def _call(self, prompt: str) -> dict[str, Any]:
        argv = [
            "claude",
            "-p",
            prompt,
            "--model",
            self.model,
            "--effort",
            self.effort,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(_OUTPUT_SCHEMA),
            "--system-prompt",
            _SYSTEM_PROMPT,
            "--tools",
            "",
            "--no-session-persistence",
        ]
        # Not inside a Claude Code session, and not inside this repository (no CLAUDE.md).
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, env=env, cwd=tempfile.gettempdir()
            )
        except OSError as e:
            raise ExtractionError(f"could not start the claude CLI: {e}") from e
        if completed.returncode != 0:
            raise ExtractionError(
                f"claude exited {completed.returncode}: {completed.stderr.strip()[-500:]}"
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"claude returned no JSON: {completed.stdout[-500:]}") from e
        if result.get("is_error"):
            raise ExtractionError(str(result.get("result")))
        output = result.get("structured_output")
        if not isinstance(output, dict):
            raise ExtractionError(f"claude returned no structured output: {result.get('result')}")
        return output

    @staticmethod
    def _to_draft(output: dict[str, Any]) -> Draft:
        draft = Draft()
        for node in output.get("nodes", []):
            draft.node(node["label"], node["key"], **node.get("properties", {}))
        for rel in output.get("relationships", []):
            draft.relate(
                draft.node(rel["start_label"], rel["start_key"]),
                rel["type"],
                draft.node(rel["end_label"], rel["end_key"]),
            )
        return draft


def make_extractor(
    name: str, *, model: str = DEFAULT_MODEL, cache_dir: Path = DEFAULT_LLM_CACHE
) -> Extractor:
    if name == "auto":
        name = "claude" if shutil.which("claude") else "rules-v2"
    if name == "rules-v1":
        return RulesV1()
    if name == "rules-v2":
        return RulesV2()
    if name == "claude":
        return ClaudeExtractor(model, cache_dir=cache_dir)
    raise ValueError(f"unknown extractor {name!r} (expected auto, rules-v1, rules-v2 or claude)")


# --- Writing the graph ---------------------------------------------------------------


def _coerce(declared_type: str | None, value: Any) -> Any:
    """Give a property the type the Declared Ontology says it has, where the value allows."""
    if declared_type == "DATE" and isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return value
    if declared_type == "INTEGER":
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
    return value


def write(graph: LocalGraph, draft: Draft, *, ontology: Ontology, database: str) -> tuple[int, int]:
    declared = {(n.label, p.name): p.type for n in ontology.node_types for p in n.properties}
    ids: dict[Key, int] = {}
    for (label, key), properties in draft.nodes.items():
        props = dict(properties)
        key_property = KEY_PROPERTY.get(label, "name")
        if key_property:
            props.setdefault(key_property, key)
        props = {name: _coerce(declared.get((label, name)), v) for name, v in props.items()}
        ids[(label, key)] = graph.add_node([label], props, database=database)
    for start, type_, end in draft.relationships:
        graph.add_relationship(ids[start], type_, ids[end])
    return len(ids), len(draft.relationships)


@dataclass(frozen=True)
class BuildStats:
    reports: int
    reports_read: int
    skipped: tuple[str, ...]  # reports the extractor could not read
    nodes: int
    relationships: int


def build(
    graph: LocalGraph,
    *,
    ontology: Ontology,
    extractor: Extractor,
    data_dir: Path = DATA_DIR,
    database: str = DEFAULT_DATABASE,
    sensors: bool = False,
) -> BuildStats:
    """Rebuild `database` in `graph` from the data: structured sources first, then every
    report through `extractor`. `sensors=True` also writes the experimental Sensor nodes
    from the condition-monitoring feed (which no Ontology Version declares)."""
    draft = load_structured(data_dir, join_technicians=extractor.joins_technicians)
    context = Context(
        machines=tuple(sorted(k for (label, k) in draft.nodes if label == "Machine")),
        technicians=tuple(sorted(k for (label, k) in draft.nodes if label == "Technician")),
    )
    reports = read_reports(data_dir)
    skipped = []
    for report, extracted in zip(
        reports, extractor.extract_all(reports, ontology, context), strict=True
    ):
        if extracted is None:
            skipped.append(report.name)
        else:
            draft.merge(extracted)
    if sensors:
        for machine in context.machines:
            sensor = draft.node(
                "Sensor", f"{machine}/vibration", name=f"{machine}/vibration", unit="mm/s"
            )
            draft.relate(draft.node("Machine", machine), "HAS_SENSOR", sensor)
    graph.clear(database)
    nodes, relationships = write(graph, draft, ontology=ontology, database=database)
    graph.save()
    return BuildStats(
        len(reports), len(reports) - len(skipped), tuple(skipped), nodes, relationships
    )


# --- Command line (the Construction Entry Point) ----------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the plant maintenance graph.")
    parser.add_argument("--ontology", required=True, help="the Declared Ontology (stetiq YAML)")
    parser.add_argument("--scope", default='{"database": "plant"}', help="Graph Source scope JSON")
    parser.add_argument(
        "--graph", default=os.environ.get("PLANT_GRAPH_FILE", str(DEFAULT_GRAPH_FILE))
    )
    parser.add_argument("--extractor", default=os.environ.get("PLANT_EXTRACTOR", "auto"))
    parser.add_argument("--model", default=os.environ.get("PLANT_EXTRACTION_MODEL", DEFAULT_MODEL))
    parser.add_argument(
        "--llm-cache", default=os.environ.get("PLANT_LLM_CACHE", str(DEFAULT_LLM_CACHE))
    )
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--sensors", action="store_true", help="also write the Sensor nodes")
    args = parser.parse_args(argv)

    ontology = parse_yaml(Path(args.ontology).read_text(encoding="utf-8"))
    database = json.loads(args.scope).get("database") or DEFAULT_DATABASE
    extractor = make_extractor(args.extractor, model=args.model, cache_dir=Path(args.llm_cache))
    try:
        stats = build(
            LocalGraph(args.graph),
            ontology=ontology,
            extractor=extractor,
            data_dir=Path(args.data_dir),
            database=database,
            sensors=args.sensors,
        )
    except ExtractionError as e:
        print(f"pipeline: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"extractor": extractor.name, **stats.__dict__}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
