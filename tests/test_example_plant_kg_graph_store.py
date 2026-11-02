"""The plant example's local graph store (examples/plant-kg/graphdb.py) reports the values
of Vocabulary-bound Attributes the way the Graph Source contract asks, like the
in-memory source does for the same data."""

import sys
from pathlib import Path

import pytest

from stetiq.graph_source import (
    BoundAttribute,
    GraphSourceScope,
    InMemoryGraphSource,
    ObservedValues,
    ValueCount,
)

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "plant-kg"
SCOPE = GraphSourceScope(database="plant")
KIND = BoundAttribute("node_type", "WorkOrder", "kind")

ORDERS = [
    {"id": "WO-1", "kind": "breakdown", "title": "Spindle"},
    {"id": "WO-2", "kind": "breakdown", "title": "Hydraulics"},
    {"id": "WO-3", "kind": "preventive", "title": "Lubrication"},
    {"id": "WO-4", "kind": "corrective", "title": "Belt"},
]


@pytest.fixture
def local_graph(tmp_path):
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        from graphdb import LocalGraph
    finally:
        sys.path.remove(str(EXAMPLE_DIR))
    graph = LocalGraph(tmp_path / "plant.json")
    for order in ORDERS:
        graph.add_node(["WorkOrder"], order, database="plant")
    graph.save()
    return graph


@pytest.fixture
def memory():
    source = InMemoryGraphSource()
    for order in ORDERS:
        source.add_node(["WorkOrder"], order, database="plant")
    return source


def kind_values(schema):
    work_orders = schema.node_type("WorkOrder")
    return {p.name: p.values for p in work_orders.properties}


def test_bound_attribute_values_are_counted_most_frequent_first(local_graph, memory):
    values = kind_values(local_graph.observe(SCOPE, [KIND]))

    assert values["kind"] == ObservedValues(
        (ValueCount("breakdown", 2), ValueCount("corrective", 1), ValueCount("preventive", 1))
    )
    assert values["title"] is None  # not bound: never read
    assert local_graph.observe(SCOPE, [KIND]) == memory.observe(SCOPE, [KIND])


def test_the_value_list_is_capped_and_flagged_truncated(local_graph, memory):
    values = kind_values(local_graph.observe(SCOPE, [KIND], value_cap=2))

    assert values["kind"] == ObservedValues(
        (ValueCount("breakdown", 2), ValueCount("corrective", 1)), truncated=True
    )
    assert local_graph.observe(SCOPE, [KIND], value_cap=2) == memory.observe(
        SCOPE, [KIND], value_cap=2
    )


def test_without_bound_attributes_no_value_is_read(local_graph):
    assert all(v is None for v in kind_values(local_graph.observe(SCOPE)).values())
