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
    Keyword arguments go to `stetiq.Client` (e.g. `client_factory(actor="ada")`).
    """
    if tracking_mode == "local":
        uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
        yield lambda **kw: stetiq.Client(uri, graph_source=graph_source, **kw)
    elif tracking_mode == "postgres":
        uri = _postgres_url()
        yield lambda **kw: stetiq.Client(uri, graph_source=graph_source, **kw)
    else:
        app = create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}")
        with TestClient(app) as http:
            yield lambda **kw: stetiq.Client(
                str(http.base_url),
                service=RemoteTrackingService(str(http.base_url), http=http),
                graph_source=graph_source,
                **kw,
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
