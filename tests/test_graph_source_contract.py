"""Contract suite for Graph Source adapters.

Every adapter must pass it. The `graph` fixture yields a harness that can seed data
(test-side writes) and exposes the adapter under test as `.source`; add a param for
each adapter (ticket #7 adds Neo4j via testcontainers, seeding through a write session).
"""

import pytest

from stetiq.graph_source import (
    Degree,
    GraphSourceScope,
    InMemoryGraphSource,
    ObservedProperty,
)


class _MemoryHarness:
    def __init__(self) -> None:
        self.source = InMemoryGraphSource()

    def add_node(self, labels, properties=None, database="neo4j"):
        return self.source.add_node(labels, properties, database=database)

    def add_relationship(self, start, type_, end, properties=None):
        return self.source.add_relationship(start, type_, end, properties)


@pytest.fixture(params=["memory"])
def graph(request):
    if request.param == "memory":
        return _MemoryHarness()
    raise AssertionError(request.param)


SCOPE = GraphSourceScope(database="neo4j", label="KG")


def test_observes_node_types_with_counts_inside_the_scope_only(graph):
    graph.add_node(["KG", "Customer"])
    graph.add_node(["KG", "Customer"])
    graph.add_node(["KG", "Customer", "Vip"])
    graph.add_node(["Customer"])  # outside the scope label
    graph.add_node(["KG", "Customer"], database="other")  # other database

    schema = graph.source.observe(SCOPE)

    assert [(n.label, n.count) for n in schema.node_types] == [("Customer", 3), ("Vip", 1)]


def test_observes_node_properties_with_types_and_fill_rates(graph):
    graph.add_node(["KG", "Customer"], {"name": "Ada", "age": 36})
    graph.add_node(["KG", "Customer"], {"name": "Bob", "age": 4.5})
    graph.add_node(["KG", "Customer"], {"name": "Cy", "tags": ["a", "b"]})
    graph.add_node(["KG", "Customer"], {"active": True})

    customer = graph.source.observe(SCOPE).node_type("Customer")

    assert customer.properties == (
        ObservedProperty("active", ("BOOLEAN",), 1, 0.25),
        ObservedProperty("age", ("FLOAT", "INTEGER"), 2, 0.5),
        ObservedProperty("name", ("STRING",), 3, 0.75),
        ObservedProperty("tags", ("LIST",), 1, 0.25),
    )


def test_observes_relationship_types_with_counts_and_property_fill_rates(graph):
    ada = graph.add_node(["KG", "Customer"])
    t1 = graph.add_node(["KG", "Ticket"])
    t2 = graph.add_node(["KG", "Ticket"])
    outside = graph.add_node(["Ticket"])
    graph.add_relationship(ada, "OPENED", t1, {"via": "email"})
    graph.add_relationship(ada, "OPENED", t2)
    graph.add_relationship(ada, "OPENED", outside, {"via": "phone"})  # endpoint out of scope

    opened = graph.source.observe(SCOPE).relationship_type("OPENED")

    assert opened.count == 2
    assert opened.properties == (ObservedProperty("via", ("STRING",), 1, 0.5),)


def test_observes_patterns_with_counts_and_cardinalities(graph):
    ada = graph.add_node(["KG", "Customer"])
    bob = graph.add_node(["KG", "Customer"])
    graph.add_node(["KG", "Customer"])  # opened nothing
    tickets = [graph.add_node(["KG", "Ticket"]) for _ in range(3)]
    graph.add_relationship(ada, "OPENED", tickets[0])
    graph.add_relationship(ada, "OPENED", tickets[1])
    graph.add_relationship(bob, "OPENED", tickets[1])
    graph.add_relationship(tickets[2], "ABOUT", ada)

    schema = graph.source.observe(SCOPE)

    assert [(p.source, p.relationship, p.target, p.count) for p in schema.patterns] == [
        ("Customer", "OPENED", "Ticket", 3),
        ("Ticket", "ABOUT", "Customer", 1),
    ]
    opened = schema.pattern("Customer", "OPENED", "Ticket")
    assert opened.out_degree == Degree(min=0, max=2, mean=1.0)
    assert opened.in_degree == Degree(min=0, max=2, mean=1.0)


def test_a_namespace_scope_selects_nodes_by_namespace_property_and_hides_it(graph):
    graph.add_node(["Customer"], {"namespace": "support", "name": "Ada"})
    graph.add_node(["Customer"], {"namespace": "sales", "name": "Bob"})

    schema = graph.source.observe(GraphSourceScope(database="neo4j", namespace="support"))

    customer = schema.node_type("Customer")
    assert customer.count == 1
    assert [p.name for p in customer.properties] == ["name"]


def test_a_database_scope_without_label_covers_the_whole_database(graph):
    graph.add_node(["Customer"])
    graph.add_node(["Ticket"])
    graph.add_node(["Ticket"], database="other")

    schema = graph.source.observe(GraphSourceScope(database="neo4j"))

    assert [(n.label, n.count) for n in schema.node_types] == [("Customer", 1), ("Ticket", 1)]


def test_an_empty_scope_has_an_empty_observed_schema(graph):
    schema = graph.source.observe(SCOPE)

    assert (schema.node_types, schema.relationship_types, schema.patterns) == ((), (), ())
