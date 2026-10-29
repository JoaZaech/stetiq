"""Shared fixtures.

Every SDK test that takes `client` (or `client_factory`) runs once per tracking
mode, so features are written once and verified in all of them:

- `local`:    in-process, SQLite file (`sqlite:///...`)
- `remote`:   SDK -> HTTP -> stetiq server (FastAPI, in-process TestClient) -> SQLite
- `postgres`: in-process over Postgres; skipped unless STETIQ_TEST_POSTGRES_URL is set
              (e.g. postgresql+psycopg://localhost/stetiq_test)
"""

import os

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.graph_source import InMemoryGraphSource
from stetiq.server import create_app
from stetiq.tracking import RemoteTrackingService

POSTGRES_URL_ENV = "STETIQ_TEST_POSTGRES_URL"


def _postgres_url() -> str:
    url = os.environ.get(POSTGRES_URL_ENV)
    if not url:
        pytest.skip(f"set {POSTGRES_URL_ENV} to run against Postgres")
    from stetiq.tracking import SqlStore

    SqlStore(url).drop_all()  # each test starts from an empty database
    return url


@pytest.fixture(params=["local", "remote", pytest.param("postgres", marks=pytest.mark.postgres)])
def tracking_mode(request):
    return request.param


@pytest.fixture
def graph_source():
    """The in-memory fake Graph Source every `client` observes; seed it in the test."""
    return InMemoryGraphSource()


@pytest.fixture
def client_factory(tracking_mode, tmp_path, graph_source):
    """Returns a function building a new `stetiq.Client` on the same backing store.

    Calling it twice gives two independent clients that see the same data, the way
    two processes sharing a tracking URI would. All of them use `graph_source`.
    """
    if tracking_mode == "local":
        uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
        yield lambda: stetiq.Client(uri, graph_source=graph_source)
    elif tracking_mode == "postgres":
        uri = _postgres_url()
        yield lambda: stetiq.Client(uri, graph_source=graph_source)
    else:
        app = create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}")
        with TestClient(app) as http:
            yield lambda: stetiq.Client(
                str(http.base_url),
                service=RemoteTrackingService(str(http.base_url), http=http),
                graph_source=graph_source,
            )


@pytest.fixture
def client(client_factory):
    return client_factory()


SUPPORT_ONTOLOGY = """
node_types:
  - label: Customer
    properties:
      - name: name
        type: STRING
        required: true
  - label: Ticket
    description: A support request
    properties:
      - name: opened_at
        type: DATE
relationship_types:
  - label: OPENED
patterns:
  - [Customer, OPENED, Ticket]
"""


@pytest.fixture
def support_ontology():
    return SUPPORT_ONTOLOGY


# --- Neo4j (testcontainers) -------------------------------------------------------------

NEO4J_IMAGE_ENV = "STETIQ_TEST_NEO4J_IMAGE"
# Enterprise (evaluation licence) so tests can create a second database for scoping.
NEO4J_DEFAULT_IMAGE = "neo4j:2026.10-enterprise"
NEO4J_DATABASES = ("neo4j", "other")


@pytest.fixture(scope="session")
def neo4j_container():
    """A throwaway Neo4j server for the whole session; skipped when Docker is unavailable."""
    try:
        import docker
        from testcontainers.community.neo4j import Neo4jContainer
    except ImportError:
        pytest.skip("testcontainers[neo4j] is not installed")
    try:
        docker.from_env().ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "no Docker here"
        pytest.skip(f"Docker is unavailable: {exc}")
    container = Neo4jContainer(
        os.environ.get(NEO4J_IMAGE_ENV, NEO4J_DEFAULT_IMAGE), password="testpassword"
    ).with_env("NEO4J_ACCEPT_LICENSE_AGREEMENT", "yes")
    with container:
        with container.get_driver() as driver:
            driver.execute_query("CREATE DATABASE other IF NOT EXISTS WAIT", database_="system")
        yield container


@pytest.fixture
def neo4j_admin_driver(neo4j_container):
    """A write-capable driver for seeding (the test plays the user's pipeline); every
    test starts with empty databases."""
    with neo4j_container.get_driver() as driver:
        for database in NEO4J_DATABASES:
            driver.execute_query("MATCH (n) DETACH DELETE n", database_=database)
        yield driver


@pytest.fixture(autouse=True)
def _no_graph_source_from_the_environment(monkeypatch):
    """Tests opt in to env-configured Graph Sources explicitly; the developer's own
    STETIQ_GRAPH_SOURCE_* settings never leak into the suite."""
    for name in ("STETIQ_GRAPH_SOURCE_URI", "STETIQ_GRAPH_SOURCE_USER", "STETIQ_GRAPH_SOURCE_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
