"""Loads one registry export into the trial-registry Knowledge Graph.

This is the Construction Entry Point named in stetiq.yaml:

    python trials_pipeline.py --ontology {ontology} --scope {graph_source}

stetiq hands it the Declared Ontology and the Graph Source scope; everything else
comes from the environment, the way a real loader gets its database credentials:

- TRIALS_EXPORT      which export folder under data/ to load (default export-2026-06)
- TRIALS_GRAPH_FILE  where the file-backed graph database lives (default .graphdb/registry.json)
- TRIALS_BIOMARKERS  "1" also writes the lab's experimental Biomarker nodes, which no
                     Ontology Version declares (the strict Evolution Mode fails the run)

The loader is deliberately plain: it writes every column the export has, whether or
not the Declared Ontology has a place for it. That is the point of the example. In a
regulated registry the Ontology is the contract, and it is stetiq's strict Evolution
Mode, not the loader, that stops an undeclared column from quietly entering the graph.
The Declared Ontology is used for one thing only: giving each property the type it
declares (a DATE string becomes a date, an INTEGER a number, a BOOLEAN a boolean).

Sources, per export folder:

| File                | Gives                                                        |
| ------------------- | ------------------------------------------------------------ |
| trials.csv          | Trial                                                        |
| sites.csv           | Site                                                         |
| trial_sites.csv     | (Trial)-[CONDUCTED_AT]->(Site)                               |
| investigators.csv   | Investigator, (Site)-[LED_BY]->(Investigator)                |
| interventions.csv   | Intervention + Drug / Device / Procedure, (Trial)-[TESTS]->  |
| conditions.csv      | Condition, (Trial)-[STUDIES]->(Condition)                    |
| arms.csv            | Arm                                                          |
| participants.csv    | Participant, ENROLLED_AT, ASSIGNED_TO                        |
| consent.csv         | (Participant)-[CONSENTED_TO]->(Trial)                        |
| adverse_events.csv  | AdverseEvent, REPORTED_IN, (Participant)-[EXPERIENCED]->     |
| visits.csv          | Visit, (Participant)-[ATTENDED]->(Visit)                     |
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trials_graph import DEFAULT_DATABASE, RegistryGraph

from stetiq.ontology import Ontology, parse_yaml

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
DEFAULT_EXPORT = "export-2026-06"
DEFAULT_GRAPH_FILE = EXAMPLE_DIR / ".graphdb" / "registry.json"

# Which columns of each table are the node's own properties (the rest are foreign keys).
_PROPERTIES = {
    "trials": ("registry_id", "title", "phase", "status"),
    "sites": ("site_id", "city", "country"),
    "investigators": ("staff_id", "specialty", "orcid"),
    "interventions": ("code", "name"),
    "conditions": ("code", "term"),
    "arms": ("code", "kind"),
    "participants": ("pseudonym", "age_band", "enrolled_on"),
    "adverse_events": ("ae_id", "severity", "serious", "onset"),
    "visits": ("visit_id", "number", "scheduled", "window_days", "deviation"),
}


@dataclass(frozen=True)
class LoadStats:
    export: str
    nodes: int
    relationships: int
    consent_rows: int


class Loader:
    """Writes one export into `graph`, typed by the Declared Ontology."""

    def __init__(self, graph: RegistryGraph, ontology: Ontology, database: str) -> None:
        self.graph = graph
        self.database = database
        self.types = {(n.label, p.name): p.type for n in ontology.node_types for p in n.properties}
        self.relationships = 0

    def node(self, label: str, row: dict[str, str], table: str, *extra_labels: str) -> int:
        labels = (label, *extra_labels)
        properties = {}
        for name in _PROPERTIES[table]:
            if row.get(name, "") == "":
                continue  # an empty cell is an absent property, not an empty string
            declared = next((self.types.get((lb, name)) for lb in labels), None)
            properties[name] = _coerce(declared or self.types.get((label, name)), row[name])
        return self.graph.add_node(labels, properties, database=self.database)

    def relate(self, start: int | None, type_: str, end: int | None) -> None:
        if start is not None and end is not None:
            self.graph.add_relationship(start, type_, end)
            self.relationships += 1


def _coerce(declared_type: str | None, value: str) -> Any:
    """Give a cell the type the Declared Ontology says the property has; otherwise guess
    from the text, so undeclared columns still land as sensible values."""
    if declared_type == "BOOLEAN" or (declared_type is None and value in ("true", "false")):
        return value == "true"
    if declared_type == "INTEGER" or (declared_type is None and value.isdigit()):
        return int(value)
    if declared_type == "DATE" or (declared_type is None and _looks_like_date(value)):
        return dt.date.fromisoformat(value)
    return value


def _looks_like_date(value: str) -> bool:
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load(
    graph: RegistryGraph,
    *,
    ontology: Ontology,
    export: str = DEFAULT_EXPORT,
    data_dir: Path = DATA_DIR,
    database: str = DEFAULT_DATABASE,
    biomarkers: bool = False,
) -> LoadStats:
    """Rebuild `database` in `graph` from the export folder `data_dir / export`."""
    folder = data_dir / export
    if not folder.is_dir():
        raise FileNotFoundError(f"no export folder {folder}")
    graph.clear(database)
    w = Loader(graph, ontology, database)

    trials = {r["registry_id"]: w.node("Trial", r, "trials") for r in _csv(folder / "trials.csv")}
    sites = {r["site_id"]: w.node("Site", r, "sites") for r in _csv(folder / "sites.csv")}
    for r in _csv(folder / "trial_sites.csv"):
        w.relate(trials.get(r["registry_id"]), "CONDUCTED_AT", sites.get(r["site_id"]))
    for r in _csv(folder / "investigators.csv"):
        w.relate(sites.get(r["site_id"]), "LED_BY", w.node("Investigator", r, "investigators"))
    for r in _csv(folder / "interventions.csv"):
        # The class column is the subtype's label: a node carries both, as Neo4j
        # models a hierarchy (Intervention is the parent declared in the Ontology).
        intervention = w.node("Intervention", r, "interventions", r["class"])
        w.relate(trials.get(r["registry_id"]), "TESTS", intervention)
    for r in _csv(folder / "conditions.csv"):
        w.relate(trials.get(r["registry_id"]), "STUDIES", w.node("Condition", r, "conditions"))
    arms = {r["code"]: w.node("Arm", r, "arms") for r in _csv(folder / "arms.csv")}

    participants: dict[str, int] = {}
    for r in _csv(folder / "participants.csv"):
        p = participants[r["pseudonym"]] = w.node("Participant", r, "participants")
        w.relate(p, "ENROLLED_AT", sites.get(r["site_id"]))
        w.relate(p, "ASSIGNED_TO", arms.get(r["arm"]))
    consent = _csv(folder / "consent.csv")
    for r in consent:
        w.relate(participants.get(r["pseudonym"]), "CONSENTED_TO", trials.get(r["registry_id"]))
    for r in _csv(folder / "adverse_events.csv"):
        event = w.node("AdverseEvent", r, "adverse_events")
        w.relate(event, "REPORTED_IN", trials.get(r["registry_id"]))
        w.relate(participants.get(r["pseudonym"]), "EXPERIENCED", event)
    for r in _csv(folder / "visits.csv"):
        w.relate(participants.get(r["pseudonym"]), "ATTENDED", w.node("Visit", r, "visits"))

    if biomarkers:
        # The lab's experimental feed: one Biomarker per trial, keyed by assay code.
        for registry_id, trial in trials.items():
            marker = graph.add_node(
                ["Biomarker"], {"assay": f"hs-CRP/{registry_id}", "unit": "mg/L"}, database=database
            )
            graph.add_relationship(trial, "MEASURES", marker)
    graph.save()
    nodes = sum(1 for n in graph._nodes.values() if n.database == database)
    return LoadStats(export, nodes, w.relationships, len(consent))


# --- Command line (the Construction Entry Point) ----------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load a registry export into the graph.")
    parser.add_argument("--ontology", required=True, help="the Declared Ontology (stetiq YAML)")
    parser.add_argument(
        "--scope", default='{"database": "registry"}', help="Graph Source scope JSON"
    )
    parser.add_argument("--export", default=os.environ.get("TRIALS_EXPORT", DEFAULT_EXPORT))
    parser.add_argument(
        "--graph", default=os.environ.get("TRIALS_GRAPH_FILE", str(DEFAULT_GRAPH_FILE))
    )
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument(
        "--biomarkers",
        action="store_true",
        default=os.environ.get("TRIALS_BIOMARKERS") == "1",
        help="also write the experimental Biomarker nodes",
    )
    args = parser.parse_args(argv)

    ontology = parse_yaml(Path(args.ontology).read_text(encoding="utf-8"))
    database = json.loads(args.scope).get("database") or DEFAULT_DATABASE
    stats = load(
        RegistryGraph(args.graph),
        ontology=ontology,
        export=args.export,
        data_dir=Path(args.data_dir),
        database=database,
        biomarkers=args.biomarkers,
    )
    print(json.dumps(stats.__dict__))
    return 0


if __name__ == "__main__":
    sys.exit(main())
