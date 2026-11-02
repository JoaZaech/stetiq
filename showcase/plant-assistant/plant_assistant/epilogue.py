"""The show's optional epilogue, after Act 3: a hand edit to the production graph shows
up as Drift."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import neo4j
import yaml

import stetiq
from plant_assistant.assistant import KG
from plant_assistant.deploy import PRODUCTION_DATABASE

CONFIG = Path(__file__).resolve().parent.parent / "stetiq.yaml"
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
    """The hand edit, then an Observation of the production graph (`observer`'s Graph
    Source must be `production`) with the Drift thresholds of `stetiq.yaml`. stetiq
    compares it with the `production` Contract Alias's Ontology Version (structural
    Drift) and with the previous Observation (statistical Drift), and records any Drift
    event."""
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
