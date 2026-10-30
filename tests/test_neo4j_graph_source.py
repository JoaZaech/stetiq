"""Neo4j-specific Graph Source behaviour beyond the shared contract suite: read-only
enforcement, Competency Question reads, and building the adapter from configuration.

Runs against the throwaway testcontainer; skipped when Docker is unavailable."""

import pytest

import stetiq
from stetiq.errors import GraphSourceWriteRejectedError
from stetiq.graph_source import GraphSourceScope, Neo4jGraphSource, graph_source_from_env

pytestmark = pytest.mark.neo4j

SCOPE = GraphSourceScope(database="neo4j", label="KG")


@pytest.fixture
def reader_credentials(neo4j_container, neo4j_admin_driver, neo4j_enterprise):
    """A least-privilege user holding only the built-in `reader` role."""
    if not neo4j_enterprise:
        pytest.skip("users with roles need a Neo4j Enterprise image")
    neo4j_admin_driver.execute_query(
        "CREATE OR REPLACE USER stetiq_reader SET PASSWORD 'readerpassword' CHANGE NOT REQUIRED",
        database_="system",
    )
    neo4j_admin_driver.execute_query("GRANT ROLE reader TO stetiq_reader", database_="system")
    return {
        "uri": neo4j_container.get_connection_url(),
        "user": "stetiq_reader",
        "password": "readerpassword",
    }


def _node_count(driver) -> int:
    records, _, _ = driver.execute_query("MATCH (n) RETURN count(n) AS c", database_="neo4j")
    return records[0]["c"]


def test_observes_with_a_read_only_user(neo4j_admin_driver, reader_credentials):
    neo4j_admin_driver.execute_query(
        "CREATE (:KG:Customer {name: 'Ada'})-[:OPENED]->(:KG:Ticket)", database_="neo4j"
    )

    with Neo4jGraphSource.connect(
        reader_credentials["uri"],
        user=reader_credentials["user"],
        password=reader_credentials["password"],
    ) as source:
        schema = source.observe(SCOPE)

    assert [(n.label, n.count) for n in schema.node_types] == [("Customer", 1), ("Ticket", 1)]
    assert schema.pattern("Customer", "OPENED", "Ticket").count == 1


def test_execute_read_returns_rows_of_a_read_query(neo4j_container, neo4j_admin_driver):
    neo4j_admin_driver.execute_query(
        "CREATE (:KG:Customer {name: 'Ada'}), (:KG:Customer {name: 'Bob'})", database_="neo4j"
    )

    with Neo4jGraphSource.connect(
        neo4j_container.get_connection_url(),
        user=neo4j_container.username,
        password=neo4j_container.password,
    ) as source:
        rows = source.execute_read(
            SCOPE,
            "MATCH (c:Customer) WHERE c.name STARTS WITH $prefix RETURN c.name AS name",
            {"prefix": "A"},
        )

    assert rows == [{"name": "Ada"}]


@pytest.mark.parametrize(
    "query",
    [
        "CREATE (:KG:Customer {name: 'Eve'})",
        "MATCH (c:Customer) SET c.name = 'Eve'",
        "MATCH (c:Customer) DETACH DELETE c",
        "CREATE INDEX customer_name IF NOT EXISTS FOR (c:Customer) ON (c.name)",
    ],
)
def test_execute_read_rejects_writes_even_with_write_privileges(
    neo4j_container, neo4j_admin_driver, query
):
    neo4j_admin_driver.execute_query("CREATE (:KG:Customer {name: 'Ada'})", database_="neo4j")

    with (
        Neo4jGraphSource.connect(
            neo4j_container.get_connection_url(),
            user=neo4j_container.username,
            password=neo4j_container.password,
        ) as source,
        pytest.raises(GraphSourceWriteRejectedError),
    ):
        source.execute_read(SCOPE, query)

    records, _, _ = neo4j_admin_driver.execute_query(
        "MATCH (c:Customer) RETURN c.name AS name", database_="neo4j"
    )
    assert [r["name"] for r in records] == ["Ada"]
    indexes, _, _ = neo4j_admin_driver.execute_query(
        "SHOW INDEXES YIELD name WHERE name = 'customer_name' RETURN name", database_="neo4j"
    )
    assert indexes == []


def test_credentials_can_be_given_in_the_uri(neo4j_container, neo4j_admin_driver):
    neo4j_admin_driver.execute_query("CREATE (:KG:Customer)", database_="neo4j")
    bolt = neo4j_container.get_connection_url()  # bolt://host:port
    uri = bolt.replace("bolt://", f"bolt://{neo4j_container.username}:{neo4j_container.password}@")

    with Neo4jGraphSource.connect(uri) as source:
        assert source.observe(SCOPE).node_type("Customer").count == 1


def test_no_adapter_is_configured_without_a_uri():
    assert graph_source_from_env({}) is None


def test_a_client_without_an_adapter_observes_the_neo4j_configured_in_the_environment(
    neo4j_container, neo4j_admin_driver, monkeypatch, tmp_path, support_ontology
):
    monkeypatch.setenv("STETIQ_GRAPH_SOURCE_URI", neo4j_container.get_connection_url())
    monkeypatch.setenv("STETIQ_GRAPH_SOURCE_USER", neo4j_container.username)
    monkeypatch.setenv("STETIQ_GRAPH_SOURCE_PASSWORD", neo4j_container.password)
    client = stetiq.Client(f"sqlite:///{tmp_path / 'stetiq.db'}")
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.bind_graph_source("support", SCOPE)

    with client.start_run("support", ontology_version=1) as run:
        neo4j_admin_driver.execute_query(
            "CREATE (:KG:Customer {name: 'Ada'})-[:OPENED]->(:KG:Ticket)", database_="neo4j"
        )

    observation = client.get_observation(client.get_run(run.id).observation_id)
    assert [(n.label, n.count) for n in observation.schema.node_types] == [
        ("Customer", 1),
        ("Ticket", 1),
    ]
    assert _node_count(neo4j_admin_driver) == 2
