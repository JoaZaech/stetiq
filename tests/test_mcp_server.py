"""`stetiq mcp`: a read-only MCP server over a `Client`, driven in-process through the
MCP SDK's in-memory client, in every tracking mode. Each tool returns what its `Client`
call returns, in the same JSON form as the CLI and the REST API."""

import json
import sys
from pathlib import Path

import anyio
import mcp
import pytest
from typer.testing import CliRunner

import stetiq
from stetiq.cli import app
from stetiq.mcp_server import create_server
from stetiq.tracking import codec, wire

USE_CASE = """
consumers:
  - id: desk
    name: Help desk
    tasks:
      - id: find
        description: Find a customer's tickets
        competency_questions: [tickets]
competency_questions:
  - id: tickets
    question: Which tickets did a customer open?
    query: MATCH (c:Customer)-[:OPENED]->(t:Ticket) RETURN c.name, t
"""


def _session(client, fn):
    """Run `fn(session)` against a server over `client`, through the in-memory client."""

    async def main():
        async with mcp.Client(create_server(client)) as session:
            return await fn(session)

    return anyio.run(main)


def _call(client, tool, **arguments):
    """Call `tool`: whether it is an error, and its text (parsed as JSON unless an error)."""

    async def call(session):
        return await session.call_tool(tool, arguments)

    result = _session(client, call)
    text = result.content[0].text
    return result.is_error, (text if result.is_error else json.loads(text))


@pytest.fixture
def support(client, support_ontology):
    """Version 1, and version 2 that drops the Customer's `name` property."""
    client.create_knowledge_graph("support", ontology=support_ontology)
    client.register_ontology(
        "support",
        support_ontology.replace(
            "      - name: name\n        type: STRING\n        required: true\n", ""
        ).replace("    properties:\n  - label: Ticket", "  - label: Ticket"),
    )
    client.register_use_case("support", USE_CASE)
    return "support"


def test_the_server_offers_exactly_the_four_read_only_tools(client):
    async def tools(session):
        return (await session.list_tools()).tools

    tools = _session(client, tools)

    assert sorted(t.name for t in tools) == [
        "consumer_impact",
        "list_knowledge_graphs",
        "ontology_diff",
        "run_context",
    ]
    assert all(t.annotations.read_only_hint for t in tools)


def test_list_knowledge_graphs_returns_each_summary_in_its_json_form(client, support):
    assert _call(client, "list_knowledge_graphs") == (
        False,
        [codec.knowledge_graph_summary_to_json(s) for s in client.list_knowledge_graphs()],
    )


def test_run_context_returns_the_run_context_as_stetiq_context_prints_it(client, support):
    assert _call(client, "run_context", knowledge_graph=support) == (
        False,
        client.run_context(support).to_dict(),
    )
    assert _call(client, "run_context", knowledge_graph=support, version=2) == (
        False,
        client.run_context(support, version=2).to_dict(),
    )


def test_run_context_carries_the_last_attempt(client, support):
    client.bind_graph_source(support, stetiq.GraphSourceScope(database="neo4j"))
    with client.start_run(support, ontology_version=2) as run:
        pass

    _, context = _call(client, "run_context", knowledge_graph=support, version=2)

    assert context["last_attempt"]["id"] == run.id


def test_ontology_diff_returns_the_classed_changes_in_their_rest_form(client, support):
    is_error, diff = _call(client, "ontology_diff", knowledge_graph=support, base=1, target=2)

    assert not is_error
    assert diff == wire.ontology_diff_to_json(client.diff_ontology_versions(support, 1, 2))
    assert diff["changes"]


def test_consumer_impact_returns_the_impact_in_its_rest_form(client, support):
    is_error, impact = _call(client, "consumer_impact", knowledge_graph=support, base=1, target=2)

    assert not is_error
    assert impact == wire.use_case_impact_to_json(client.consumer_impact(support, 1, 2))
    assert impact["consumers"][0]["level"] == "affected"


@pytest.mark.parametrize(
    ("tool", "client_call", "arguments"),
    [
        ("run_context", "run_context", {"knowledge_graph": "nope"}),
        ("run_context", "run_context", {"knowledge_graph": "support", "version": 99}),
        (
            "ontology_diff",
            "diff_ontology_versions",
            {"knowledge_graph": "support", "base": 1, "target": 99},
        ),
        (
            "consumer_impact",
            "consumer_impact",
            {"knowledge_graph": "nope", "base": 1, "target": 2},
        ),
    ],
)
def test_an_unknown_knowledge_graph_or_version_is_a_tool_error_with_stetiqs_message(
    client, support, tool, client_call, arguments
):
    with pytest.raises(stetiq.StetiqError) as raised:
        getattr(client, client_call)(*arguments.values())

    is_error, text = _call(client, tool, **arguments)

    assert is_error
    assert str(raised.value) in text


def test_the_instructions_state_the_loops_rules(client):
    async def instructions(session):
        return session.instructions

    text = _session(client, instructions)

    assert "only where a Competency Question needs it" in text
    assert "declare the question in the Use Case first" in text
    assert "names a symptom, not a cause" in text
    assert "You propose; a person accepts" in text
    assert "`stetiq gate` and `stetiq consumer gate`" in text


# --- `stetiq mcp`, the CLI command -------------------------------------------------------


def test_stetiq_mcp_completes_a_stdio_handshake_and_lists_its_tools(tmp_path, support_ontology):
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    stetiq.Client(uri).create_knowledge_graph("support", ontology=support_ontology)
    server = mcp.StdioServerParameters(
        command=str(Path(sys.executable).parent / "stetiq"),
        args=["mcp", "--tracking-uri", uri],
    )

    async def main():
        with anyio.fail_after(30):
            async with mcp.Client(server) as session:
                tools = (await session.list_tools()).tools
                listed = await session.call_tool("list_knowledge_graphs", {})
                return sorted(t.name for t in tools), json.loads(listed.content[0].text)

    names, graphs = anyio.run(main)

    assert names == ["consumer_impact", "list_knowledge_graphs", "ontology_diff", "run_context"]
    assert [g["name"] for g in graphs] == ["support"]


def test_stetiq_mcp_without_the_mcp_package_exits_1_with_an_install_hint(monkeypatch):
    for name in [n for n in sys.modules if n == "mcp" or n.startswith("mcp.")]:
        monkeypatch.setitem(sys.modules, name, None)  # importing it now raises ImportError
    monkeypatch.delitem(sys.modules, "stetiq.mcp_server", raising=False)

    result = CliRunner().invoke(app, ["mcp"])

    assert result.exit_code == 1
    assert "uv sync --extra mcp" in result.output
    assert "pip install 'stetiq[mcp]'" in result.output
