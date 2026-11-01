"""Builds the plant maintenance Knowledge Graph from the plant's own data.

Sources, under data/:

| Source                      | Kind         | Gives                                              |
| --------------------------- | ------------ | -------------------------------------------------- |
| assets/machines.csv         | structured   | Machine, Line, PART_OF                             |
| assets/material_flow.json   | structured   | FEEDS, as drawn in the layout (can be stale)       |
| cmms/work_orders.csv        | structured   | WorkOrder, PERFORMED_ON, ASSIGNED_TO, Technician   |
| hr/technicians.csv          | structured   | Technician.badge                                   |
| reports/*.txt, *.eml        | unstructured | Component, FollowUp, Fault, Supplier, FEEDS stated in prose |

The structured sources load deterministically. Claude reads the technicians' reports,
one `claude -p` call per report, guided by the Declared Ontology stetiq hands the run.
There are two prompt versions, and each round of the demo picks one:

| Round | Prompt | Declared Ontology (chosen by the demo, or `stetiq run --version`) |
| ----- | ------ | ------------------------------------------------------------------ |
| v1    | v1     | ontology/v1.yaml                                                   |
| v2    | v2     | production (v1)                                                    |
| fix   | v2     | ontology/fix.yaml                                                  |

Prompt v2 also pulls suppliers out of the reports and fills a work order's fields from
its report where the report is more specific; the pipeline lets the report's `kind`
override the CMMS export's.

Claude's answers are cached by (prompt version, model, prompt). Three modes:

- `replay` (default): read the committed cache in llm-cache/ only. A miss is an error,
  so a changed prompt never calls Claude silently.
- `live`: call the `claude` CLI on a miss and cache to the gitignored .graphdb/llm-cache/.
- `record`: call the `claude` CLI for every report and overwrite the committed entries.

Run it as the Construction Entry Point (see stetiq.yaml):

    PLANT_ROUND=v2 python pipeline.py --ontology declared.yaml --scope '{"database": "plant"}'

Environment: PLANT_ROUND (or --round), PLANT_GRAPH_FILE (where the local graph store
lives), PLANT_LLM (`replay`, `live` or `record`), PLANT_EXTRACTION_MODEL and
PLANT_LLM_CACHE (a cache folder other than the mode's own).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from graphdb import DEFAULT_DATABASE, LocalGraph

from stetiq.ontology import Ontology, parse_yaml, to_yaml

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
DEFAULT_GRAPH_FILE = EXAMPLE_DIR / ".graphdb" / "plant.json"
RECORDED_LLM_CACHE = EXAMPLE_DIR / "llm-cache"  # committed: the demo's recording
SCRATCH_LLM_CACHE = EXAMPLE_DIR / ".graphdb" / "llm-cache"  # gitignored: --live
DEFAULT_MODEL = "claude-opus-5-5"

Round = Literal["v1", "v2", "fix"]
ROUNDS: tuple[Round, ...] = ("v1", "v2", "fix")
PROMPT_OF_ROUND: dict[Round, str] = {"v1": "v1", "v2": "v2", "fix": "v2"}
LlmMode = Literal["replay", "live", "record"]
LLM_MODES: tuple[LlmMode, ...] = ("replay", "live", "record")

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
    are never overwritten by what a report says, unless the pipeline says otherwise
    (see `build`)."""

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


def load_structured(data_dir: Path = DATA_DIR) -> Draft:
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
            downtime_minutes=int(row["downtime_minutes"]),
        )
        draft.relate(order, "PERFORMED_ON", draft.node("Machine", row["machine_id"]))
        draft.relate(order, "ASSIGNED_TO", draft.node("Technician", row["technician"]))
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
    """What the structured sources already know, handed to the extractor."""

    machines: tuple[str, ...]
    technicians: tuple[str, ...]


_WORK_ORDER_ID = re.compile(r"\bWO-\d{4}\b")


class ExtractionError(Exception):
    """The Claude Code CLI could not produce an extraction."""


class CacheMissError(ExtractionError):
    """Replay mode found no recorded answer for a prompt."""


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

_KEYS_RULE = (
    "- Keys: Machine, the asset id as written (e.g. CNC-04). WorkOrder, its id (e.g. "
    'WO-2031). Technician, the full name. Component, the part name in lower case, singular, as written in the report (e.g. "spindle bearing"). '
    'Supplier, the vendor name. Fault, the work order id (one root cause per work order). FollowUp, "<work order id>#<n>", numbered from 1 in the order they appear.'
)
_VALUES_RULE = (
    "- Property values follow the declared type: DATE as YYYY-MM-DD, INTEGER as a number, "
    'STRING as text. A FollowUp\'s status is "open" or "done".'
)

# Each prompt version's rules. v1 is the pipeline's first prompt; v2 is the change the
# demo's second round makes.
_RULES = {
    "v1": f"""- Use only the node labels, property names, relationship types and patterns the ontology declares, and leave out facts it has no place for. Relationship direction follows the patterns.
{_KEYS_RULE}
{_VALUES_RULE}
- The work order, its machine, its technician and its date already come from the CMMS export: emit those nodes with their key only. Attach what the report adds: the components the work involved, the follow-ups with their owner, the root cause, the supplier a replacement component was ordered from, and material-flow statements between machines (one machine feeding or supplying parts to another).""",
    "v2": f"""- Use the node labels, property names, relationship types and patterns the ontology declares. One addition the ontology may not have yet: record the supplier a replacement component was ordered from as a Supplier node (property name) with a relationship (Component)-[SUPPLIED_BY]->(Supplier). Leave out other facts the ontology has no place for. Relationship direction follows the patterns.
{_KEYS_RULE}
{_VALUES_RULE}
- Read the whole report, whatever its format (a form, a free-text note or an email), and pull out the root cause and the supplier of every replacement part wherever they are stated.
- The work order, its machine, its technician and its date also come from the CMMS export, but the technician's report is the source of truth for the job. Emit the machine and the technician with their key only. Emit the work order with its key and every declared property the report states or clearly implies, taking the report's characterisation of the job over the CMMS export's wherever the report is more specific. Attach what the report adds: the components the work involved, the follow-ups with their owner, the root cause, the supplier a replacement component was ordered from, and material-flow statements between machines (one machine feeding or supplying parts to another).""",
}


class ClaudeExtractor:
    """Extraction by Claude through the Claude Code CLI, guided by the Declared Ontology.

    Each report is one `claude -p` call with a JSON schema for the output, no tools and
    a replaced system prompt. Answers are cached by (prompt version, model, prompt); each
    entry keeps the response as Claude returned it, with its model and recording date.
    """

    workers = 4

    def __init__(
        self,
        prompt_version: str,
        *,
        model: str = DEFAULT_MODEL,
        mode: LlmMode = "replay",
        cache_dir: Path | None = None,
        effort: str = "low",
    ) -> None:
        if prompt_version not in _RULES:
            raise ValueError(f"unknown prompt version {prompt_version!r}")
        self.prompt_version = prompt_version
        self.model = model
        self.mode: LlmMode = mode
        self.cache_dir = Path(
            cache_dir or (SCRATCH_LLM_CACHE if mode == "live" else RECORDED_LLM_CACHE)
        )
        self.effort = effort
        self.calls = 0
        self.cache_hits = 0

    @property
    def report_kind_overrides(self) -> bool:
        """Whether a report's WorkOrder.kind replaces the CMMS export's (prompt v2)."""
        return self.prompt_version == "v2"

    def extract_all(
        self, reports: Sequence[Report], ontology: Ontology, context: Context
    ) -> list[Draft]:
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(lambda r: self.extract(r, ontology, context), reports))

    def extract(self, report: Report, ontology: Ontology, context: Context) -> Draft:
        prompt = self._prompt(report, ontology, context)
        key = hashlib.sha256(f"{self.prompt_version}\n{self.model}\n{prompt}".encode()).hexdigest()
        cached = self.cache_dir / f"{key}.json"
        if self.mode != "record" and cached.exists():
            self.cache_hits += 1
            entry = json.loads(cached.read_text(encoding="utf-8"))
            return self._to_draft(entry["response"])
        if self.mode == "replay":
            raise CacheMissError(
                f"cache miss for {report.name} (prompt {self.prompt_version}, {self.model}) in "
                f"{self.cache_dir}, rerun with --record"
            )
        print(
            f"  extracting {report.name} with {self.model} (prompt {self.prompt_version}) ...",
            file=sys.stderr,
        )
        response = self._call(prompt)
        self.calls += 1
        entry = {
            "prompt_version": self.prompt_version,
            "model": self.model,
            "recorded_at": dt.date.today().isoformat(),
            "report": report.name,
            "response": response,
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(entry, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return self._to_draft(response)

    def _prompt(self, report: Report, ontology: Ontology, context: Context) -> str:
        order = _WORK_ORDER_ID.search(report.text)
        return f"""Extract the property graph stated by the maintenance report below.

## Declared Ontology (stetiq YAML)

{to_yaml(ontology)}
## Rules

{_RULES[self.prompt_version]}

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


def extractor_for_round(
    round_: Round,
    *,
    model: str = DEFAULT_MODEL,
    mode: LlmMode = "replay",
    cache_dir: Path | None = None,
) -> ClaudeExtractor:
    return ClaudeExtractor(PROMPT_OF_ROUND[round_], model=model, mode=mode, cache_dir=cache_dir)


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
    nodes: int
    relationships: int


def build(
    graph: LocalGraph,
    *,
    ontology: Ontology,
    extractor: ClaudeExtractor,
    data_dir: Path = DATA_DIR,
    database: str = DEFAULT_DATABASE,
) -> BuildStats:
    """Rebuild `database` in `graph` from the data: structured sources first, then every
    report through `extractor`."""
    draft = load_structured(data_dir)
    context = Context(
        machines=tuple(sorted(k for (label, k) in draft.nodes if label == "Machine")),
        technicians=tuple(sorted(k for (label, k) in draft.nodes if label == "Technician")),
    )
    reports = read_reports(data_dir)
    for extracted in extractor.extract_all(reports, ontology, context):
        draft.merge(extracted)
        if extractor.report_kind_overrides:
            for (label, key), props in extracted.nodes.items():
                if label == "WorkOrder" and props.get("kind") is not None:
                    draft.nodes[(label, key)]["kind"] = props["kind"]
    graph.clear(database)
    nodes, relationships = write(graph, draft, ontology=ontology, database=database)
    graph.save()
    return BuildStats(len(reports), nodes, relationships)


# --- Command line (the Construction Entry Point) ----------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the plant maintenance graph.")
    parser.add_argument("--ontology", required=True, help="the Declared Ontology (stetiq YAML)")
    parser.add_argument("--scope", default='{"database": "plant"}', help="Graph Source scope JSON")
    parser.add_argument(
        "--round",
        choices=ROUNDS,
        default=os.environ.get("PLANT_ROUND"),
        help="which round's prompt to extract with (default: $PLANT_ROUND)",
    )
    parser.add_argument(
        "--graph", default=os.environ.get("PLANT_GRAPH_FILE", str(DEFAULT_GRAPH_FILE))
    )
    parser.add_argument("--model", default=os.environ.get("PLANT_EXTRACTION_MODEL", DEFAULT_MODEL))
    parser.add_argument("--llm", choices=LLM_MODES, default=os.environ.get("PLANT_LLM", "replay"))
    parser.add_argument("--llm-cache", default=os.environ.get("PLANT_LLM_CACHE"))
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    args = parser.parse_args(argv)
    if args.round is None:
        parser.error("say which round to run: --round v1|v2|fix, or set PLANT_ROUND")

    ontology = parse_yaml(Path(args.ontology).read_text(encoding="utf-8"))
    database = json.loads(args.scope).get("database") or DEFAULT_DATABASE
    extractor = extractor_for_round(
        cast(Round, args.round),
        model=args.model,
        mode=cast(LlmMode, args.llm),
        cache_dir=Path(args.llm_cache) if args.llm_cache else None,
    )
    try:
        stats = build(
            LocalGraph(args.graph),
            ontology=ontology,
            extractor=extractor,
            data_dir=Path(args.data_dir),
            database=database,
        )
    except ExtractionError as e:
        print(f"pipeline: {e}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "round": args.round,
                "prompt": extractor.prompt_version,
                "model": extractor.model,
                "llm": extractor.mode,
                "claude_calls": extractor.calls,
                "cache_hits": extractor.cache_hits,
                **stats.__dict__,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
