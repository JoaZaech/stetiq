"""The Ontology Map: layout, labels, selection, paths, search and changes between versions."""

from __future__ import annotations

import json
from typing import Any

import stetiq

from ._shared import Scenario

# For the Ontology Map: two relations between Customer and Ticket, a self-loop, Agent and
# Customer under Party, and a deprecated class (LegacyTicket) and relation (FILED).
MAP_ONTOLOGY = """
node_types:
  - {label: Agent, parent: Party}
  - {label: Customer, parent: Party}
  - {label: LegacyTicket, parent: Ticket, deprecated: true}
  - Party
  - Product
  - Ticket
relationship_types: [ABOUT, DUPLICATES, {label: FILED, deprecated: true}, FOLLOWS, OPENED]
patterns:
  - [Customer, OPENED, Ticket]
  - [Customer, FOLLOWS, Ticket]
  - [Ticket, ABOUT, Product]
  - [Ticket, DUPLICATES, Ticket]
  - [Customer, FILED, LegacyTicket]
"""


# MAP_ONTOLOGY's next version: Queue and IN_QUEUE added (additive), Product and ABOUT
# removed (breaking), and Ticket given a required property (breaking).
MAP_ONTOLOGY_V2 = """
node_types:
  - {label: Agent, parent: Party}
  - {label: Customer, parent: Party}
  - {label: LegacyTicket, parent: Ticket, deprecated: true}
  - Party
  - Queue
  - label: Ticket
    properties: [{name: priority, type: STRING, required: true}]
relationship_types: [DUPLICATES, {label: FILED, deprecated: true}, FOLLOWS, IN_QUEUE, OPENED]
patterns:
  - [Customer, OPENED, Ticket]
  - [Customer, FOLLOWS, Ticket]
  - [Ticket, DUPLICATES, Ticket]
  - [Customer, FILED, LegacyTicket]
  - [Ticket, IN_QUEUE, Queue]
"""


# MAP_ONTOLOGY_V2's next version: Team and MEMBER_OF added (additive), and Queue
# deprecated (deprecating). Against v1, Queue is an addition instead.
MAP_ONTOLOGY_V3 = """
node_types:
  - {label: Agent, parent: Party}
  - {label: Customer, parent: Party}
  - {label: LegacyTicket, parent: Ticket, deprecated: true}
  - Party
  - {label: Queue, deprecated: true}
  - Team
  - label: Ticket
    properties: [{name: priority, type: STRING, required: true}]
relationship_types:
  [DUPLICATES, {label: FILED, deprecated: true}, FOLLOWS, IN_QUEUE, MEMBER_OF, OPENED]
patterns:
  - [Customer, OPENED, Ticket]
  - [Customer, FOLLOWS, Ticket]
  - [Ticket, DUPLICATES, Ticket]
  - [Customer, FILED, LegacyTicket]
  - [Ticket, IN_QUEUE, Queue]
  - [Agent, MEMBER_OF, Team]
"""


def ontology_map(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_ONTOLOGY`, v2 = `MAP_ONTOLOGY_V2` and
    v3 = `MAP_ONTOLOGY_V3`."""
    client.create_knowledge_graph("support", ontology=MAP_ONTOLOGY)
    client.register_ontology("support", MAP_ONTOLOGY_V2)
    client.register_ontology("support", MAP_ONTOLOGY_V3)
    return {}


# Two Patterns of one relation: v2 adds (Agent)-[OPENED]->(Ticket) beside v1's
# (Customer)-[OPENED]->(Ticket), so the Diff records an endpoint change against OPENED.
MAP_PATTERNS_V1 = """
node_types: [Agent, Customer, Ticket]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""


MAP_PATTERNS_V2 = MAP_PATTERNS_V1.replace(
    "patterns: [[Customer, OPENED, Ticket]]",
    "patterns: [[Agent, OPENED, Ticket], [Customer, OPENED, Ticket]]",
)


def ontology_map_patterns(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_PATTERNS_V1` and v2 = `MAP_PATTERNS_V2`."""
    client.create_knowledge_graph("support", ontology=MAP_PATTERNS_V1)
    client.register_ontology("support", MAP_PATTERNS_V2)
    return {}


# A relation whose first changed Pattern a filter hides: v2 adds OPENED from Agent to the
# deprecated LegacyTicket and to Ticket, beside v1's unchanged (Customer)-[OPENED]->(Ticket).
MAP_HIDDEN_PATTERN_V1 = """
node_types: [Agent, Customer, {label: LegacyTicket, deprecated: true}, Ticket]
relationship_types: [OPENED]
patterns: [[Customer, OPENED, Ticket]]
"""


MAP_HIDDEN_PATTERN_V2 = MAP_HIDDEN_PATTERN_V1.replace(
    "patterns: [[Customer, OPENED, Ticket]]",
    "patterns: [[Agent, OPENED, LegacyTicket], [Agent, OPENED, Ticket], [Customer, OPENED, Ticket]]",
)


def ontology_map_hidden_pattern(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_HIDDEN_PATTERN_V1` and v2 = `MAP_HIDDEN_PATTERN_V2`."""
    client.create_knowledge_graph("support", ontology=MAP_HIDDEN_PATTERN_V1)
    client.register_ontology("support", MAP_HIDDEN_PATTERN_V2)
    return {}


# Changed attributes on the Ontology Map: v2 renames Stop.wheelchairBoarding to
# wheelchair_boarding and makes Stop.name required; Stop.code and Route are untouched.
MAP_ATTRIBUTES_V1 = """
node_types:
  - label: Route
    properties: [{name: short_name, type: STRING}]
  - label: Stop
    properties:
      - {name: code, type: STRING}
      - {name: name, type: STRING}
      - {name: wheelchairBoarding, type: INTEGER}
relationship_types: [SERVES]
patterns: [[Route, SERVES, Stop]]
"""


MAP_ATTRIBUTES_V2 = MAP_ATTRIBUTES_V1.replace(
    "{name: name, type: STRING}", "{name: name, type: STRING, required: true}"
).replace("wheelchairBoarding", "wheelchair_boarding")


def ontology_map_attributes(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `transit` with v1 = `MAP_ATTRIBUTES_V1` and v2 = `MAP_ATTRIBUTES_V2`."""
    client.create_knowledge_graph("transit", ontology=MAP_ATTRIBUTES_V1)
    client.register_ontology("transit", MAP_ATTRIBUTES_V2)
    return {}


# For selecting on the Ontology Map: a superclass, properties, a constraint, a described relation.
MAP_DETAILS_ONTOLOGY = """
node_types:
  - label: Party
    properties: [{name: name, type: STRING, required: true}]
  - label: Customer
    parent: Party
    description: Someone who opens tickets
    properties: [{name: email, type: STRING}]
  - {label: Product}
  - label: Ticket
    properties: [{name: opened_at, type: DATE}]
relationship_types:
  - label: OPENED
    description: The customer opened the ticket
    properties: [{name: channel, type: STRING}]
  - {label: ABOUT}
patterns:
  - [Customer, OPENED, Ticket]
  - [Ticket, ABOUT, Product]
constraints:
  - {type: UNIQUENESS, node_type: Customer, property_name: email}
"""


def ontology_map_details(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_DETAILS_ONTOLOGY`."""
    client.create_knowledge_graph("support", ontology=MAP_DETAILS_ONTOLOGY)
    return {}


# For paths on the Ontology Map: Customer reaches Address only through its superclass Party's
# Pattern, and nothing connects Agent.
MAP_PATH_ONTOLOGY = """
node_types:
  - {label: Address}
  - {label: Agent}
  - {label: Party}
  - {label: Customer, parent: Party}
  - {label: Product}
  - {label: Ticket}
relationship_types:
  - {label: ABOUT}
  - {label: LIVES_AT}
  - {label: OPENED}
patterns:
  - [Customer, OPENED, Ticket]
  - [Party, LIVES_AT, Address]
  - [Ticket, ABOUT, Product]
"""


def ontology_map_path(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = `MAP_PATH_ONTOLOGY`."""
    client.create_knowledge_graph("support", ontology=MAP_PATH_ONTOLOGY)
    return {}


def ontology_map_large(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `support` with v1 = 60 classes in a ring, each related to the next:
    an Ontology too big for the Map's viewport at a readable zoom."""
    labels = [f"Class{i:02}" for i in range(60)]
    ontology = {
        "node_types": labels,
        "relationship_types": ["NEXT"],
        "patterns": [[a, "NEXT", b] for a, b in zip(labels, labels[1:] + labels[:1], strict=True)],
    }
    # JSON is YAML.
    client.create_knowledge_graph("support", ontology=json.dumps(ontology))
    return {}


# Like examples/transit-network-kg: v2 (a Candidate's) takes the feed's camelCase columns,
# v3 renames them to snake_case (two breaking removals, two additions) and documents HAS_TRIP.
MAP_TRANSIT_V2 = """
node_types:
  - {label: Agency}
  - {label: Route}
  - label: Stop
    properties: [{name: wheelchairBoarding, type: INTEGER}]
  - label: Trip
    properties: [{name: bikesAllowed, type: INTEGER}]
relationship_types: [HAS_TRIP, OPERATES, SERVES]
patterns:
  - [Agency, OPERATES, Route]
  - [Route, HAS_TRIP, Trip]
  - [Trip, SERVES, Stop]
"""


MAP_TRANSIT_V3 = (
    MAP_TRANSIT_V2.replace("wheelchairBoarding", "wheelchair_boarding")
    .replace("bikesAllowed", "bikes_allowed")
    .replace(
        "relationship_types: [HAS_TRIP,",
        "relationship_types: [{label: HAS_TRIP, description: The scheduled trips of a route},",
    )
)


def ontology_map_transit(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `city-transit` with v1 = `MAP_TRANSIT_V2` without its attributes,
    v2 = `MAP_TRANSIT_V2` and v3 = `MAP_TRANSIT_V3`."""
    v1 = MAP_TRANSIT_V2.replace(
        "    properties: [{name: wheelchairBoarding, type: INTEGER}]\n", ""
    ).replace("    properties: [{name: bikesAllowed, type: INTEGER}]\n", "")
    client.create_knowledge_graph("city-transit", ontology=v1)
    client.register_ontology("city-transit", MAP_TRANSIT_V2)
    client.register_ontology("city-transit", MAP_TRANSIT_V3)
    return {}


# For searching the Ontology Map, from the retail-orders example: Bin mentions warehouses in
# its description and an attribute without being one, and so does SHIPPED_FROM's description.
MAP_SEARCH_ONTOLOGY = """
node_types:
  - label: Bin
    description: A storage location inside a warehouse
    properties: [{name: code, type: STRING}, {name: warehouse, type: STRING}]
  - {label: Order}
  - {label: Shipment}
  - {label: Warehouse, description: A fulfilment site shipments leave from}
relationship_types:
  - {label: FULFILLS}
  - {label: SHIPPED_FROM, description: The warehouse a shipment left}
  - {label: STORED_IN}
patterns:
  - [Shipment, FULFILLS, Order]
  - [Shipment, SHIPPED_FROM, Warehouse]
  - [Bin, STORED_IN, Warehouse]
"""


def ontology_map_search(client: stetiq.Client) -> dict[str, Any]:
    """Knowledge Graph `retail` with v1 = `MAP_SEARCH_ONTOLOGY`."""
    client.create_knowledge_graph("retail", ontology=MAP_SEARCH_ONTOLOGY)
    return {}


SCENARIOS: tuple[Scenario, ...] = (
    ontology_map,
    ontology_map_patterns,
    ontology_map_hidden_pattern,
    ontology_map_attributes,
    ontology_map_details,
    ontology_map_path,
    ontology_map_large,
    ontology_map_transit,
    ontology_map_search,
)
