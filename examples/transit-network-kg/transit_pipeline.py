"""Builds the city-transit Knowledge Graph from a GTFS feed and the operator's other systems.

This is the Construction Entry Point of stetiq.yaml:

    python transit_pipeline.py --ontology {ontology} --scope {graph_source}

Sources:

| Source                        | Gives                                                      |
| ----------------------------- | ---------------------------------------------------------- |
| <feed>/agency.txt             | Agency, OPERATES                                           |
| <feed>/routes.txt             | Route                                                      |
| <feed>/trips.txt              | Trip, HAS_TRIP, RUNS_ON                                    |
| <feed>/stops.txt              | Stop, PARENT_STATION (from the parent_station column)      |
| <feed>/stop_times.txt         | StopTime, HAS_STOP_TIME, AT_STOP                           |
| <feed>/calendar.txt           | Service                                                    |
| depots.csv                    | Depot, OPERATED_FROM (the depot register, not GTFS)        |
| fare_zones.json               | FareZone, IN_ZONE (the fare system, not GTFS)              |

The operator files are taken from the feed folder when a feed bundle ships them, else
from data/. Environment: TRANSIT_FEED_DIR (default data/gtfs) and TRANSIT_GRAPH_FILE
(default .graphdb/transit.json). These are the pipeline's own settings, read the way a
real pipeline reads its database credentials; stetiq knows nothing about them.

Naming: the standard GTFS columns map to the property names the ontology was written
with (route_short_name -> short_name) and relationship types are the GTFS reference
column in UPPER_SNAKE_CASE (parent_station -> PARENT_STATION). Any other column is
written under the name the Declared Ontology spells it, if it declares one that matches
ignoring case and underscores; otherwise as the feed spells it. The feed exporter writes
its optional columns in camelCase (wheelchairBoarding, bikesAllowed), so until the
Declared Ontology names them, the graph carries the vendor's spelling and a Candidate
inherits it. That is what the naming_conventions Evaluator is there to catch.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transit_graph import DEFAULT_DATABASE, TransitGraph

from stetiq.ontology import Ontology, parse_yaml

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
DEFAULT_FEED_DIR = DATA_DIR / "gtfs"
DEFAULT_GRAPH_FILE = EXAMPLE_DIR / ".graphdb" / "transit.json"

Key = tuple[str, str]  # (label, key)

# Standard GTFS columns -> property name. Columns that end up as relationships are listed
# in RELATIONSHIP_COLUMNS; anything else is an extra column (see the module docstring).
KNOWN_COLUMNS: dict[str, dict[str, str]] = {
    "Agency": {
        "agency_id": "id",
        "agency_name": "name",
        "agency_url": "url",
        "agency_timezone": "timezone",
    },
    "Route": {
        "route_id": "id",
        "route_short_name": "short_name",
        "route_long_name": "long_name",
        "route_type": "route_type",
    },
    "Trip": {"trip_id": "id", "trip_headsign": "headsign", "direction_id": "direction_id"},
    "Stop": {
        "stop_id": "id",
        "stop_name": "name",
        "stop_lat": "lat",
        "stop_lon": "lon",
        "location_type": "location_type",
    },
    "StopTime": {
        "arrival_time": "arrival_time",
        "departure_time": "departure_time",
        "stop_sequence": "stop_sequence",
    },
}
RELATIONSHIP_COLUMNS: dict[str, set[str]] = {
    "Route": {"agency_id"},
    "Trip": {"route_id", "service_id"},
    "Stop": {"parent_station"},
    "StopTime": {"trip_id", "stop_id"},
}
FLOAT_COLUMNS = {"stop_lat", "stop_lon"}
# Columns whose values are text even when they look like numbers: tram 1's
# route_short_name is "1", a name, not a count.
TEXT_COLUMNS = {"route_short_name", "trip_headsign", "stop_name"}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _snake(name: str) -> str:
    """`wheelchairBoarding` and `wheelchair_boarding` both become `wheelchair_boarding`."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).replace("-", "_").lower()


def spelled(ontology: Ontology, label: str, column: str) -> str:
    """The Declared Ontology's spelling of an extra feed column, else the feed's own."""
    declared = [p.name for n in ontology.node_types if n.label == label for p in n.properties]
    return next((name for name in declared if _snake(name) == _snake(column)), column)


def _value(column: str, raw: str) -> Any:
    if raw == "":
        return None
    if column in FLOAT_COLUMNS:
        return float(raw)
    if column in TEXT_COLUMNS:
        return raw
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


def _properties(ontology: Ontology, label: str, row: dict[str, str]) -> dict[str, Any]:
    known = KNOWN_COLUMNS.get(label, {})
    skip = RELATIONSHIP_COLUMNS.get(label, set())
    props: dict[str, Any] = {}
    for column, raw in row.items():
        if column in skip:
            continue
        name = known.get(column) or spelled(ontology, label, column)
        value = _value(column, raw)
        if value is not None:
            props[name] = value
    return props


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _operator_file(feed_dir: Path, data_dir: Path, name: str) -> Path:
    bundled = feed_dir / name
    return bundled if bundled.exists() else data_dir / name


@dataclass(frozen=True)
class BuildStats:
    feed: str
    nodes: int
    relationships: int
    routes: int
    trips: int
    stop_times: int


def build(
    graph: TransitGraph,
    *,
    ontology: Ontology,
    feed_dir: Path = DEFAULT_FEED_DIR,
    data_dir: Path = DATA_DIR,
    database: str = DEFAULT_DATABASE,
) -> BuildStats:
    """Rebuild `database` in `graph` from the feed: truncate the scope, then write every
    node and relationship the sources state. Properties follow the naming rule above."""
    graph.clear(database)
    ids: dict[Key, int] = {}
    relationships = 0

    def node(label: str, key: str, row: dict[str, str]) -> int:
        node_id = graph.add_node([label], _properties(ontology, label, row), database=database)
        ids[(label, key)] = node_id
        return node_id

    def relate(start: Key, type_: str, end: Key) -> None:
        nonlocal relationships
        if start in ids and end in ids:
            graph.add_relationship(ids[start], type_, ids[end])
            relationships += 1

    for row in _csv(feed_dir / "agency.txt"):
        node("Agency", row["agency_id"], row)
    for row in _csv(feed_dir / "routes.txt"):
        node("Route", row["route_id"], row)
        relate(("Agency", row["agency_id"]), "OPERATES", ("Route", row["route_id"]))
    for row in _csv(feed_dir / "calendar.txt"):
        graph_row = {
            "id": row["service_id"],
            "days": "".join(row[day] for day in WEEKDAYS),
        }
        node_id = graph.add_node(
            ["Service"],
            {
                **graph_row,
                "start_date": dt.datetime.strptime(row["start_date"], "%Y%m%d").date(),
                "end_date": dt.datetime.strptime(row["end_date"], "%Y%m%d").date(),
            },
            database=database,
        )
        ids[("Service", row["service_id"])] = node_id
    for row in _csv(feed_dir / "stops.txt"):
        node("Stop", row["stop_id"], row)
    for row in _csv(feed_dir / "stops.txt"):
        if row.get("parent_station"):
            relate(("Stop", row["stop_id"]), "PARENT_STATION", ("Stop", row["parent_station"]))
    trips = _csv(feed_dir / "trips.txt")
    for row in trips:
        node("Trip", row["trip_id"], row)
        relate(("Route", row["route_id"]), "HAS_TRIP", ("Trip", row["trip_id"]))
        relate(("Trip", row["trip_id"]), "RUNS_ON", ("Service", row["service_id"]))
    stop_times = _csv(feed_dir / "stop_times.txt")
    for n, row in enumerate(stop_times):
        key = f"{row['trip_id']}#{n}"
        node("StopTime", key, row)
        relate(("Trip", row["trip_id"]), "HAS_STOP_TIME", ("StopTime", key))
        relate(("StopTime", key), "AT_STOP", ("Stop", row["stop_id"]))

    for row in _csv(_operator_file(feed_dir, data_dir, "depots.csv")):
        depot = {"depot_id": row["depot_id"], "name": row["name"], "address": row["address"]}
        node_id = graph.add_node(
            ["Depot"], {"id": depot["depot_id"], **_without(depot, "depot_id")}, database=database
        )
        ids[("Depot", row["depot_id"])] = node_id
        for route_id in filter(None, row["routes"].split(";")):
            relate(("Route", route_id), "OPERATED_FROM", ("Depot", row["depot_id"]))
    zones = json.loads(
        _operator_file(feed_dir, data_dir, "fare_zones.json").read_text(encoding="utf-8")
    )
    for zone in zones["zones"]:
        node_id = graph.add_node(
            ["FareZone"], {"id": zone["id"], "name": zone["name"]}, database=database
        )
        ids[("FareZone", zone["id"])] = node_id
        for stop_id in zone["stops"]:
            relate(("Stop", stop_id), "IN_ZONE", ("FareZone", zone["id"]))

    graph.save()
    return BuildStats(
        feed=feed_dir.name,
        nodes=len(ids),
        relationships=relationships,
        routes=sum(1 for label, _ in ids if label == "Route"),
        trips=len(trips),
        stop_times=len(stop_times),
    )


def _without(d: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k != key}


# --- Command line (the Construction Entry Point) ----------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the city-transit graph from a GTFS feed.")
    parser.add_argument("--ontology", required=True, help="the Declared Ontology (stetiq YAML)")
    parser.add_argument(
        "--scope", default=json.dumps({"database": DEFAULT_DATABASE}), help="Graph Source scope"
    )
    parser.add_argument(
        "--feed-dir", default=os.environ.get("TRANSIT_FEED_DIR", str(DEFAULT_FEED_DIR))
    )
    parser.add_argument(
        "--graph", default=os.environ.get("TRANSIT_GRAPH_FILE", str(DEFAULT_GRAPH_FILE))
    )
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    args = parser.parse_args(argv)

    ontology = parse_yaml(Path(args.ontology).read_text(encoding="utf-8"))
    database = json.loads(args.scope).get("database") or DEFAULT_DATABASE
    feed_dir = Path(args.feed_dir)
    if not (feed_dir / "stops.txt").is_file():
        print(f"transit_pipeline: {feed_dir} is not a GTFS feed folder", file=sys.stderr)
        return 1
    stats = build(
        TransitGraph(args.graph),
        ontology=ontology,
        feed_dir=feed_dir,
        data_dir=Path(args.data_dir),
        database=database,
    )
    print(json.dumps(stats.__dict__))
    return 0


if __name__ == "__main__":
    sys.exit(main())
