"""API-token authentication in server mode.

These tests talk to a stetiq server (in-process) through the public SDK. Tokens are
issued the way an administrator would: against the server's database.
"""

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.server import create_app
from stetiq.tracking import RemoteTrackingService


@pytest.fixture
def server(tmp_path, graph_source):
    database_url = f"sqlite:///{tmp_path / 'server.db'}"
    with TestClient(create_app(database_url)) as http:
        yield database_url, http, graph_source


def _client(server, token=None, **kw):
    _, http, graph_source = server
    url = str(http.base_url)
    service = RemoteTrackingService(url, http=http, token=token)
    return stetiq.Client(url, service=service, graph_source=graph_source, **kw)


def _issue(server, user, grants):
    _, value = TokenRegistry(server[0]).issue(user, grants)
    return value


@pytest.fixture
def support(server, support_ontology):
    """A `support` Knowledge Graph with Ontology Versions 1 and 2, created by an admin."""
    admin = _client(server, _issue(server, "admin", {"*": "edit"}))
    admin.create_knowledge_graph("support", ontology=support_ontology)
    admin.register_ontology("support", support_ontology.replace("A support request", "A ticket"))
    admin.bind_graph_source("support", stetiq.GraphSourceScope(database="neo4j"))
    return "support"


def test_requests_without_a_token_are_rejected(server):
    with pytest.raises(stetiq.AuthenticationError):
        _client(server).get_knowledge_graph("support")


def test_a_valid_token_is_accepted(server, support):
    reader = _client(server, _issue(server, "ada", {"support": "read"}))

    assert reader.get_knowledge_graph(support).name == "support"


def test_an_unknown_token_is_rejected(server, support):
    with pytest.raises(stetiq.AuthenticationError):
        _client(server, "stq_nope_nope").get_knowledge_graph(support)


def test_a_revoked_token_is_rejected(server, support):
    registry = TokenRegistry(server[0])
    token, value = registry.issue("ada", {"support": "read"})
    registry.revoke(token.id)

    with pytest.raises(stetiq.AuthenticationError):
        _client(server, value).get_knowledge_graph(support)


def test_read_permission_allows_fetching(server, support):
    reader = _client(server, _issue(server, "ada", {"support": "read"}))

    assert [v.number for v in reader.list_ontology_versions(support)] == [1, 2]
    assert reader.get_alias(support, "production").version == 1
    assert [p.alias for p in reader.list_promotions(support)] == ["production"]


def test_registering_needs_edit_permission(server, support, support_ontology):
    reader = _client(server, _issue(server, "ada", {"support": "read"}))

    with pytest.raises(stetiq.PermissionDeniedError):
        reader.register_ontology(support, support_ontology.replace("A support request", "x"))
    assert len(reader.list_ontology_versions(support)) == 2


def test_moving_an_alias_needs_edit_permission(server, support):
    reader = _client(server, _issue(server, "ada", {"support": "read"}))

    with pytest.raises(stetiq.PermissionDeniedError):
        reader.set_alias(support, "production", 2)
    assert reader.get_alias(support, "production").version == 1


def test_running_needs_edit_permission(server, support):
    reader = _client(server, _issue(server, "ada", {"support": "read"}))

    with pytest.raises(stetiq.PermissionDeniedError):
        reader.start_run(support, ontology_version=1)
    assert reader.list_runs(support) == []


def test_naming_a_steward_or_authority_needs_edit_permission(server, support):
    reader = _client(server, _issue(server, "ada", {"support": "read"}))

    with pytest.raises(stetiq.PermissionDeniedError):
        reader.set_knowledge_graph_governance(support, steward="Ada")
    with pytest.raises(stetiq.PermissionDeniedError):
        reader.set_knowledge_graph_governance(support, authority="Ops board")
    kg = reader.get_knowledge_graph(support)
    assert (kg.steward, kg.authority) == (None, None)


def test_edit_permission_allows_registering_running_and_moving_aliases(
    server, support, support_ontology
):
    editor = _client(server, _issue(server, "ada", {"support": "edit"}))

    version = editor.register_ontology(support, support_ontology.replace("A support request", "y"))
    editor.set_alias(support, "production", version.number)
    run = editor.start_run(support)

    assert editor.get_alias(support, "production").version == 3
    assert [r.id for r in editor.list_runs(support)] == [run.id]


def test_permissions_are_per_knowledge_graph(server, support, support_ontology):
    admin = _client(server, _issue(server, "admin", {"*": "edit"}))
    admin.create_knowledge_graph("billing", ontology=support_ontology)
    support_editor = _client(server, _issue(server, "ada", {"support": "edit"}))

    with pytest.raises(stetiq.PermissionDeniedError):
        support_editor.get_knowledge_graph("billing")
    with pytest.raises(stetiq.PermissionDeniedError):
        support_editor.create_knowledge_graph("hr", ontology=support_ontology)


def test_listing_knowledge_graphs_shows_only_those_the_token_can_read(
    server, support, support_ontology
):
    admin = _client(server, _issue(server, "admin", {"*": "edit"}))
    admin.create_knowledge_graph("billing", ontology=support_ontology)
    support_reader = _client(server, _issue(server, "ada", {"support": "read"}))

    assert [s.knowledge_graph.name for s in support_reader.list_knowledge_graphs()] == ["support"]
    assert [s.knowledge_graph.name for s in admin.list_knowledge_graphs()] == ["billing", "support"]
    with pytest.raises(stetiq.AuthenticationError):
        _client(server).list_knowledge_graphs()


def test_the_audit_log_records_the_tokens_user_as_actor(server, support):
    ada = _client(server, _issue(server, "ada", {"support": "edit"}), actor="someone-else")

    ada.set_alias(support, "production", 2)

    assert ada.list_promotions(support)[-1].actor == "ada"
