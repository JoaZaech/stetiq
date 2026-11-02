"""`stetiq mcp`: a read-only MCP server for the coding agents that improve an upstream
pipeline (Claude Code, Cursor).

A thin layer over a `Client` with no domain rules: each tool calls one `Client` method and
returns its JSON form, the same as the CLI and the REST API (`RunContext.to_dict`, the
codec and wire functions). No tool writes. A `StetiqError` becomes a tool error carrying
stetiq's message. Needs the optional `mcp` dependency (`pip install 'stetiq[mcp]'`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from stetiq.client import Client
from stetiq.errors import StetiqError
from stetiq.tracking import codec, wire

INSTRUCTIONS = """\
stetiq versions, evaluates and governs the Ontology of a Knowledge Graph. These tools are \
read-only: they show how the upstream pipeline's output was judged, so you can improve the \
pipeline. Start with `list_knowledge_graphs`, then `run_context` for the Knowledge Graph \
you are working on.

The rules of the loop:
1. Extend the Ontology only where a Competency Question needs it. If a change needs a \
question that the Use Case does not have yet, declare the question in the Use Case first; \
a Concept no Competency Question needs is an unjustified addition.
2. A Consumer Gate verdict names a symptom, not a cause. A question that lost rows tells \
you what broke for a Consumer, not why; find the cause in the Ontology Diff and the \
pipeline before you change anything.
3. You propose; a person accepts. Your change goes into a pull request, where \
`stetiq gate` and `stetiq consumer gate` judge it and a person decides. Never treat your \
own change as accepted.
"""

_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)


def _json_result(call: Callable[[], Any]) -> CallToolResult:
    """Run one `Client` call and return its JSON form as the tool's text; a
    `StetiqError` becomes a tool error with stetiq's message."""
    try:
        data = call()
    except StetiqError as e:
        raise ToolError(str(e)) from e
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))]
    )


def create_server(client: Client) -> MCPServer:
    """The `stetiq mcp` server over `client`: four read-only tools and the loop's rules
    as its `instructions`."""
    server = MCPServer(name="stetiq", instructions=INSTRUCTIONS)

    @server.tool(annotations=_READ_ONLY, structured_output=False)
    def list_knowledge_graphs() -> CallToolResult:
        """Every Knowledge Graph you can read, with a summary of its state (as
        `stetiq kg list` and `GET /api/v1/knowledge-graphs`)."""
        return _json_result(
            lambda: [
                codec.knowledge_graph_summary_to_json(s) for s in client.list_knowledge_graphs()
            ]
        )

    @server.tool(annotations=_READ_ONLY, structured_output=False)
    def run_context(knowledge_graph: str, version: int | None = None) -> CallToolResult:
        """The Run Context of a Knowledge Graph, as `stetiq context` prints it: the
        Ontology Version to extract against (`version`, default the Contract Alias's),
        the Use Case it must serve, how that version scores and how the latest runs
        against it were judged. Structure only, never instance data."""
        return _json_result(lambda: client.run_context(knowledge_graph, version=version).to_dict())

    @server.tool(annotations=_READ_ONLY, structured_output=False)
    def ontology_diff(knowledge_graph: str, base: int, target: int) -> CallToolResult:
        """The Ontology Diff from Ontology Version `base` to `target`, each change classed
        cosmetic, additive, deprecating or breaking (as `GET …/ontology-diff`)."""
        return _json_result(
            lambda: wire.ontology_diff_to_json(
                client.diff_ontology_versions(knowledge_graph, base, target)
            )
        )

    @server.tool(annotations=_READ_ONLY, structured_output=False)
    def consumer_impact(knowledge_graph: str, base: int, target: int) -> CallToolResult:
        """Which Consumers, Tasks and Competency Questions of the latest Use Case Version
        the Ontology Diff from `base` to `target` hits (as `GET …/consumer-impact`)."""
        return _json_result(
            lambda: wire.use_case_impact_to_json(
                client.consumer_impact(knowledge_graph, base, target)
            )
        )

    return server
