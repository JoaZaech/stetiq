"""Contract suite for Graph Source adapters.

Every adapter must pass it. The `graph` fixture yields a harness that can seed data
(test-side writes) and exposes the adapter under test as `.source`; add a param for
each adapter (`neo4j` runs a throwaway testcontainer, seeding through a write session, and is
skipped when Docker is unavailable).
"""

import pytest

from stetiq.graph_source import (
    BoundAttribute,
    Degree,
    GraphSourceScope,
    InMemoryGraphSource,
    Neo4jGraphSource,
    ObservedProperty,
    ObservedValues,
    OutsideBounds,
    PatternBound,
    ValueCount,
)


class _MemoryHarness:
    def __init__(self) -> None:
        self.source = InMemoryGraphSource()

    def add_node(self, labels, properties=None, database="neo4j"):
        return self.source.add_node(labels, properties, database=database)

    def add_relationship(self, start, type_, end, properties=None):
        return self.source.add_relationship(start, type_, end, properties)


class _Neo4jHarness:
    """Seeds through a write session on the testcontainer; `.source` is the adapter."""

    def __init__(self, driver, container, databases) -> None:
        self._driver = driver
        self._databases = databases
        self.source = Neo4jGraphSource.connect(
            container.get_connection_url(), user=container.username, password=container.password
        )

    def add_node(self, labels, properties=None, database="neo4j"):
        if database not in self._databases:
            # Community has a single database: the out-of-scope node can't exist, so
            # database scoping is only exercised against an Enterprise image.
            return (database, None)
        label_expr = ":".join(f"`{label}`" for label in labels)
        records, _, _ = self._driver.execute_query(
            f"CREATE (n:{label_expr}) SET n = $props RETURN elementId(n) AS id",
            props=properties or {},
            database_=database,
        )
        return (database, records[0]["id"])

    def add_relationship(self, start, type_, end, properties=None):
        (database, start_id), (end_database, end_id) = start, end
        assert database == end_database, "a relationship cannot span databases"
        self._driver.execute_query(
            f"MATCH (a), (b) WHERE elementId(a) = $a AND elementId(b) = $b "
            f"CREATE (a)-[r:`{type_}`]->(b) SET r = $props",
            a=start_id,
            b=end_id,
            props=properties or {},
            database_=database,
        )

    def close(self) -> None:
        self.source.close()


@pytest.fixture(params=["memory", pytest.param("neo4j", marks=pytest.mark.neo4j)])
def graph(request):
    if request.param == "memory":
        yield _MemoryHarness()
    elif request.param == "neo4j":
        harness = _Neo4jHarness(
            request.getfixturevalue("neo4j_admin_driver"),
            request.getfixturevalue("neo4j_container"),
            request.getfixturevalue("neo4j_databases"),
        )
        yield harness
        harness.close()
    else:
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


def seed_tickets_opened(graph):
    """Customers opening 2, 1 and 0 of three in-scope Tickets (the third one twice
    opened), plus an edge to a Ticket outside the scope, which is not counted."""
    ada = graph.add_node(["KG", "Customer"])
    bob = graph.add_node(["KG", "Customer"])
    graph.add_node(["KG", "Customer"])  # opened nothing
    tickets = [graph.add_node(["KG", "Ticket"]) for _ in range(3)]
    graph.add_relationship(ada, "OPENED", tickets[0])
    graph.add_relationship(ada, "OPENED", tickets[1])
    graph.add_relationship(bob, "OPENED", tickets[1])
    graph.add_relationship(bob, "OPENED", graph.add_node(["Ticket"]))  # endpoint out of scope


def test_counts_the_endpoint_nodes_outside_each_declared_pattern_bound(graph):
    seed_tickets_opened(graph)
    bounds = [
        PatternBound("Customer", "OPENED", "Ticket", "out", 1, 1),  # ada (2) and the idle one (0)
        PatternBound("Customer", "OPENED", "Ticket", "in", None, 1),  # the twice-opened Ticket
    ]

    opened = graph.source.observe(SCOPE, pattern_bounds=bounds).pattern(
        "Customer", "OPENED", "Ticket"
    )

    assert opened.out_degree.outside_bounds == OutsideBounds(min=1, max=1, count=2)
    assert opened.in_degree.outside_bounds == OutsideBounds(min=None, max=1, count=1)


def test_a_minimum_counts_zero_degree_endpoint_nodes_against_it(graph):
    seed_tickets_opened(graph)
    bound = PatternBound("Customer", "OPENED", "Ticket", "in", 1, None)

    opened = graph.source.observe(SCOPE, pattern_bounds=[bound]).pattern(
        "Customer", "OPENED", "Ticket"
    )

    assert opened.in_degree.outside_bounds == OutsideBounds(min=1, max=None, count=1)
    assert opened.out_degree.outside_bounds is None  # no bound in that direction


def test_without_declared_bounds_nothing_is_counted(graph):
    seed_tickets_opened(graph)

    opened = graph.source.observe(SCOPE).pattern("Customer", "OPENED", "Ticket")

    assert (opened.out_degree.outside_bounds, opened.in_degree.outside_bounds) == (None, None)


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


def test_observes_values_with_counts_for_a_requested_node_attribute(graph):
    for status in ["open", "open", "closed", "open", "blocked", "closed"]:
        graph.add_node(["KG", "Ticket"], {"status": status})
    graph.add_node(["KG", "Ticket"], {"status": 3})  # not a string: no Vocabulary Value
    graph.add_node(["Ticket"], {"status": "outside"})  # outside the scope label

    schema = graph.source.observe(SCOPE, (BoundAttribute("node_type", "Ticket", "status"),))

    assert schema.node_type("Ticket").properties[0].values == ObservedValues(
        (ValueCount("open", 3), ValueCount("closed", 2), ValueCount("blocked", 1)),
        truncated=False,
    )


def test_values_are_capped_and_truncated_only_when_more_distinct_values_exist(graph):
    for status in ["open", "open", "open", "closed", "closed", "blocked"]:
        graph.add_node(["KG", "Ticket"], {"status": status})
    for priority in ["high", "low", "low"]:
        graph.add_node(["KG", "Ticket"], {"priority": priority})

    schema = graph.source.observe(
        SCOPE,
        (
            BoundAttribute("node_type", "Ticket", "status"),
            BoundAttribute("node_type", "Ticket", "priority"),
        ),
        value_cap=2,
    )

    priority, status = schema.node_type("Ticket").properties
    assert status.values == ObservedValues(
        (ValueCount("open", 3), ValueCount("closed", 2)), truncated=True
    )
    assert priority.values == ObservedValues(
        (ValueCount("low", 2), ValueCount("high", 1)), truncated=False
    )


def test_observes_values_of_a_requested_relationship_attribute(graph):
    ada = graph.add_node(["KG", "Customer"])
    ticket = graph.add_node(["KG", "Ticket"])
    outside = graph.add_node(["Ticket"])
    graph.add_relationship(ada, "OPENED", ticket, {"channel": "email"})
    graph.add_relationship(ada, "OPENED", ticket, {"channel": "phone"})
    graph.add_relationship(ada, "OPENED", ticket, {"channel": "email"})
    graph.add_relationship(ada, "OPENED", outside, {"channel": "fax"})  # endpoint out of scope

    schema = graph.source.observe(
        SCOPE, (BoundAttribute("relationship_type", "OPENED", "channel"),)
    )

    assert schema.relationship_type("OPENED").properties[0].values == ObservedValues(
        (ValueCount("email", 2), ValueCount("phone", 1)), truncated=False
    )


def test_reads_no_values_for_attributes_that_were_not_requested(graph):
    ada = graph.add_node(["KG", "Customer"], {"name": "Ada", "status": "vip"})
    ticket = graph.add_node(["KG", "Ticket"], {"status": "open", "title": "Broken"})
    graph.add_relationship(ada, "OPENED", ticket, {"status": "new"})

    schema = graph.source.observe(SCOPE, (BoundAttribute("node_type", "Ticket", "status"),))

    observed = {
        (owner.label, p.name): p.values
        for owner in (*schema.node_types, *schema.relationship_types)
        for p in owner.properties
    }
    assert observed == {
        ("Customer", "name"): None,
        ("Customer", "status"): None,
        ("Ticket", "status"): ObservedValues((ValueCount("open", 1),), truncated=False),
        ("Ticket", "title"): None,
        ("OPENED", "status"): None,
    }
