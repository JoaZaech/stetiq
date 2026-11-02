"""Builds the plant maintenance Knowledge Graph from the plant's own data.

Sources, under data/:

| Source                      | Kind         | Gives                                              |
| --------------------------- | ------------ | -------------------------------------------------- |
| assets/machines.csv         | structured   | Machine, Line, PART_OF                             |
| assets/material_flow.json   | structured   | FEEDS, as drawn in the layout (can be stale)       |
| cmms/work_orders.csv        | structured   | WorkOrder, PERFORMED_ON, ASSIGNED_TO, Technician   |
| cmms/eam_line2_orders.csv   | structured   | The same, for Line 2, from the new EAM system      |
| hr/technicians.csv          | structured   | Technician.badge                                   |
| reports/*.txt, *.eml        | unstructured | Component, FollowUp, Fault, FEEDS stated in prose, and what Claude adds |

The structured sources load deterministically. Claude reads the technicians' reports,
one `claude -p` call per report. Its prompt carries the run context stetiq hands the
pipeline (`Client.run_context`): the Ontology Version as a suggestion, the Consumers'
Tasks and Competency Questions with how each ran last time, and the version's
evaluation results. Claude may extend the Ontology where a Competency Question needs it,
and returns a Definition for every Concept it adds; the pipeline proposes those to the
run (`ActiveRun.propose_definitions`), so the Candidate carries them.

There are two prompt versions, and each round of the demo picks one:

| Round | Prompt | Work order exports            | Declared Ontology  |
| ----- | ------ | ----------------------------- | ------------------ |
| v1    | v1     | legacy CMMS                   | ontology/v1.yaml   |
| v2    | v2     | Line 2's EAM, then legacy     | production (v1)    |
| fix   | v2     | Line 2's EAM, then legacy     | ontology/fix.yaml  |

Prompt v2 also reads the email report for root causes and suppliers, and fills a work
order's fields from its report where the report is more specific. The same change takes
in the export of Line 2's new maintenance system (EAM), its system of record for Line 2's
work orders, so its rows win over the legacy CMMS's copy. A work order's `kind` is copied
from the export, as it always was, and the EAM's order types call a breakdown
`corrective`. Where the Declared Ontology binds `WorkOrder.kind` to a Vocabulary and the
export's code is not one of its Vocabulary Values, the pipeline takes the `kind` Claude
read from the report, if that is one (Claude sees the Vocabulary in the Ontology).

Claude's answers are cached by (prompt version, model, prompt). Three modes:

- `replay` (default): read the committed cache in llm-cache/ only. A miss is an error,
  so a changed prompt never calls Claude silently.
- `live`: call the `claude` CLI on a miss and cache to the gitignored .graphdb/llm-cache/.
- `record`: call the `claude` CLI for every report and overwrite the committed entries.

Two ways to run a round:

- `run_round(client, ...)`, SDK instrumentation: starts the Construction Run, builds,
  proposes Claude's Definitions and ends the run. demo.py uses it.
- As the Construction Entry Point of stetiq.yaml (`PLANT_ROUND=v2 stetiq run`). The
  run context comes from the tracking database read-only, but an entry point process
  has no way to propose Definitions to the run, so Concepts Claude adds stay
  undocumented in the Candidate.

Environment: PLANT_ROUND (or --round), PLANT_GRAPH_FILE (where the local graph store
lives), PLANT_LLM (`replay`, `live` or `record`), PLANT_EXTRACTION_MODEL,
PLANT_LLM_CACHE (a cache folder other than the mode's own) and STETIQ_TRACKING_URI.
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

import stetiq
from stetiq.ontology import Ontology, to_yaml
from stetiq.run_context import RunContext

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
    """Nodes and relationships one source contributes, merged by (label, key), plus the
    Definitions Claude gives for Concepts it adds (by Concept reference).

    The first value seen for a property wins, so the structured sources (loaded first)
    are never overwritten by what a report says, unless the pipeline says otherwise
    (see `build`)."""

    nodes: dict[Key, dict[str, Any]] = field(default_factory=dict)
    relationships: list[tuple[Key, str, Key]] = field(default_factory=list)
    definitions: dict[str, str] = field(default_factory=dict)

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
        for concept, definition in other.definitions.items():
            self.definitions.setdefault(concept, definition)


# --- Structured sources ----------------------------------------------------------------


@dataclass(frozen=True)
class WorkOrderExport:
    """One maintenance system's work order export, and the names of its columns."""

    path: str  # under data/
    id: str
    machine: str
    kind: str
    opened_at: str
    technician: str
    downtime_minutes: str
    title: str


LEGACY_CMMS = WorkOrderExport(
    "cmms/work_orders.csv",
    "work_order_id",
    "machine_id",
    "kind",
    "opened_at",
    "technician",
    "downtime_minutes",
    "title",
)
# Line 2 moved to a new EAM system; its export is the system of record for Line 2.
LINE2_EAM = WorkOrderExport(
    "cmms/eam_line2_orders.csv",
    "order_number",
    "equipment",
    "order_type",
    "created_on",
    "responsible",
    "downtime_min",
    "short_text",
)
# In order: the first export holding a work order gives its fields.
EXPORTS_OF_ROUND: dict[Round, tuple[WorkOrderExport, ...]] = {
    "v1": (LEGACY_CMMS,),
    "v2": (LINE2_EAM, LEGACY_CMMS),
    "fix": (LINE2_EAM, LEGACY_CMMS),
}


def load_structured(
    data_dir: Path = DATA_DIR, exports: Sequence[WorkOrderExport] = (LEGACY_CMMS,)
) -> Draft:
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
    for export in exports:
        for row in _csv(data_dir / export.path):
            order = draft.node(
                "WorkOrder",
                row[export.id],
                id=row[export.id],
                title=row[export.title],
                kind=row[export.kind],
                opened_at=dt.date.fromisoformat(row[export.opened_at]),
                downtime_minutes=int(row[export.downtime_minutes]),
            )
            draft.relate(order, "PERFORMED_ON", draft.node("Machine", row[export.machine]))
            draft.relate(order, "ASSIGNED_TO", draft.node("Technician", row[export.technician]))
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
    """What the structured sources already know, and the run context stetiq hands the
    pipeline, as the prompt shows it."""

    machines: tuple[str, ...]
    technicians: tuple[str, ...]
    run_context: str


def describe_run_context(context: RunContext) -> str:
    """The run context as prompt text: the Ontology Version as a suggestion, what each
    Competency Question is for and how it ran last time, and the version's evaluation
    metrics. Only Ontology, Use Case, metrics and counts (ADR 0001)."""
    data = context.to_dict()
    lines = [
        f"## Ontology Version {context.ontology_version.number} (a suggestion, stetiq YAML)",
        "",
        to_yaml(context.ontology_version.ontology),
        "## What the graph is for",
        "",
    ]
    use_case = context.use_case_version.use_case if context.use_case_version else None
    for consumer in use_case.consumers if use_case else ():
        for task in consumer.tasks:
            lines.append(
                f"- {consumer.name} ({consumer.id}), Task {task.id}: {task.description}. "
                f"Competency Questions: {', '.join(task.competency_questions)}"
            )
    lines += ["", "## Competency Questions, and how each ran on the latest run", ""]
    for q in data["competency_questions"]:
        serves = ", ".join(f"{s['consumer']}/{s['task']}" for s in q["serves"]) or "no Task"
        execution = q["execution"]
        ran = (
            "not executed"
            if execution is None
            else f"{execution['status']}, {execution['rows']} rows"
        )
        lines.append(f'- {q["id"]}: "{q["question"]}" Serves: {serves}. Last run: {ran}.')
    lines += [
        "",
        f"## Evaluation results of Ontology Version {context.ontology_version.number}",
        "",
    ]
    for result in sorted(data["evaluation_results"], key=lambda r: r["evaluator"]):
        metrics = ", ".join(f"{k}={_number(v)}" for k, v in sorted(result["metrics"].items()))
        lines.append(f"- {result['evaluator']}: {metrics}")
    return "\n".join(lines)


def _number(value: float) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


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
        "definitions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "definition": {"type": "string"},
                },
                "required": ["concept", "definition"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nodes", "relationships", "definitions"],
    "additionalProperties": False,
}

_ONTOLOGY_RULE = (
    "- The ontology is a suggestion. Use its node labels, property names, relationship "
    "types and patterns. Where a Competency Question needs a Concept the ontology lacks "
    "(a node label, a relationship type or a property), you may add it; add nothing no "
    "Competency Question needs, and leave out facts that have no place. Relationship "
    "direction follows the patterns.\n"
    "- For every Concept you add, return a one-sentence Definition in `definitions`, "
    "keyed by its reference: the label for a node label or relationship type, "
    "`Label.property` for a property. Return no Definition for a Concept the ontology "
    "already has."
)
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
    "v1": f"""{_ONTOLOGY_RULE}
{_KEYS_RULE}
{_VALUES_RULE}
- The work order, its machine, its technician and its date already come from the CMMS export: emit those nodes with their key only. Attach what the report adds: the components the work involved, the follow-ups with their owner, the root cause, and material-flow statements between machines (one machine feeding or supplying parts to another).""",
    "v2": f"""{_ONTOLOGY_RULE}
{_KEYS_RULE}
{_VALUES_RULE}
- Read the whole report, whatever its format (a form, a free-text note or an email), and pull out the root cause and the supplier of every replacement part wherever they are stated.
- The work order, its machine, its technician and its date also come from the CMMS export, whose fields are filled in quickly and are often generic. Emit the machine and the technician with their key only. Emit the work order with its key, and fill in its properties from the report where the report is more specific than a generic CMMS entry. Attach what the report adds: the components the work involved, the follow-ups with their owner, the root cause, the supplier a replacement component was ordered from, and material-flow statements between machines (one machine feeding or supplying parts to another).""",
}


class ClaudeExtractor:
    """Extraction by Claude through the Claude Code CLI, guided by the run context.

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

    def extract_all(self, reports: Sequence[Report], context: Context) -> list[Draft]:
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(lambda r: self.extract(r, context), reports))

    def extract(self, report: Report, context: Context) -> Draft:
        prompt = self._prompt(report, context)
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

    def _prompt(self, report: Report, context: Context) -> str:
        order = _WORK_ORDER_ID.search(report.text)
        return f"""Extract the property graph stated by the maintenance report below.

{context.run_context}

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
        for d in output.get("definitions", []):
            if d["concept"].strip() and d["definition"].strip():
                draft.definitions.setdefault(d["concept"].strip(), d["definition"].strip())
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
    definitions: dict[str, str]  # Claude's Definitions for the Concepts it added


def _kind_values(ontology: Ontology) -> frozenset[str] | None:
    """The Vocabulary Values `WorkOrder.kind` is bound to; None when it is not bound."""
    bound = next(
        (
            p.vocabulary
            for n in ontology.node_types
            if n.label == "WorkOrder"
            for p in n.properties
            if p.name == "kind"
        ),
        None,
    )
    vocabulary = next((v for v in ontology.vocabularies if v.label == bound), None)
    return None if vocabulary is None else frozenset(v.label for v in vocabulary.values)


def build(
    graph: LocalGraph,
    *,
    context: RunContext,
    extractor: ClaudeExtractor,
    exports: Sequence[WorkOrderExport] = (LEGACY_CMMS,),
    data_dir: Path = DATA_DIR,
    database: str = DEFAULT_DATABASE,
) -> BuildStats:
    """Rebuild `database` in `graph` from the data: the structured sources and the work
    order `exports` first, then every report through `extractor`, prompted with the run
    context."""
    ontology = context.ontology_version.ontology
    kinds = _kind_values(ontology)
    draft = load_structured(data_dir, exports)
    prompt_context = Context(
        machines=tuple(sorted(k for (label, k) in draft.nodes if label == "Machine")),
        technicians=tuple(sorted(k for (label, k) in draft.nodes if label == "Technician")),
        run_context=describe_run_context(context),
    )
    reports = read_reports(data_dir)
    for extracted in extractor.extract_all(reports, prompt_context):
        draft.merge(extracted)
        if kinds is None:
            continue
        # A bound kind: an export code outside the Vocabulary gives way to Claude's.
        for (label, key), props in extracted.nodes.items():
            order = draft.nodes[(label, key)]
            if (
                label == "WorkOrder"
                and order.get("kind") not in kinds
                and props.get("kind") in kinds
            ):
                order["kind"] = props["kind"]
    graph.clear(database)
    nodes, relationships = write(graph, draft, ontology=ontology, database=database)
    graph.save()
    return BuildStats(len(reports), nodes, relationships, dict(draft.definitions))


def run_round(
    client: stetiq.Client,
    knowledge_graph: str,
    round_: Round,
    *,
    graph: LocalGraph,
    ontology_version: int | None = None,
    model: str = DEFAULT_MODEL,
    mode: LlmMode = "replay",
    data_dir: Path = DATA_DIR,
) -> stetiq.ConstructionRun:
    """One round as an SDK-instrumented Construction Run: its Declared Ontology is
    `ontology_version` (default the Contract Alias's). Claude's Definitions for the
    Concepts it adds are proposed to the run before it ends."""
    extractor = extractor_for_round(round_, model=model, mode=mode)
    with client.start_run(knowledge_graph, ontology_version=ontology_version) as run:
        context = client.run_context(knowledge_graph, version=run.ontology_version)
        run.log_params(
            {"round": round_, "prompt": extractor.prompt_version, "model": model, "llm": mode}
        )
        stats = build(
            graph,
            context=context,
            extractor=extractor,
            exports=EXPORTS_OF_ROUND[round_],
            data_dir=data_dir,
            database=client.get_graph_source(knowledge_graph).database,
        )
        run.log_metrics({"nodes": stats.nodes, "relationships": stats.relationships})
        if stats.definitions:
            run.propose_definitions(stats.definitions)
    return client.get_run(run.id)


# --- Command line (the Construction Entry Point) ----------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the plant maintenance graph.")
    parser.add_argument("--knowledge-graph", required=True)
    parser.add_argument("--ontology-version", type=int, required=True)
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

    # Read-only: the run context of the version `stetiq run` declared for this run.
    context = stetiq.Client().run_context(args.knowledge_graph, version=args.ontology_version)
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
            context=context,
            extractor=extractor,
            exports=EXPORTS_OF_ROUND[cast(Round, args.round)],
            data_dir=Path(args.data_dir),
            database=database,
        )
    except ExtractionError as e:
        print(f"pipeline: {e}", file=sys.stderr)
        return 1
    if stats.definitions:
        print(
            "pipeline: an entry point cannot propose Definitions to its run; Concepts Claude "
            f"added stay undocumented ({', '.join(sorted(stats.definitions))})",
            file=sys.stderr,
        )
    print(
        json.dumps(
            {
                "round": args.round,
                "prompt": extractor.prompt_version,
                "model": extractor.model,
                "llm": extractor.mode,
                "claude_calls": extractor.calls,
                "cache_hits": extractor.cache_hits,
                "reports": stats.reports,
                "nodes": stats.nodes,
                "relationships": stats.relationships,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
