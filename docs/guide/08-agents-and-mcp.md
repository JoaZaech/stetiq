# Agents and MCP

A coding agent such as Claude Code or Cursor can help you improve your upstream pipeline, but only if it can see how the pipeline's last output was judged. `stetiq mcp` gives it that view: a local [MCP](https://modelcontextprotocol.io) server that serves the [run context](./03-python-sdk.md#the-run-context), your Knowledge Graphs, Ontology Diffs and Consumer impact. The words used here are explained on the [Concepts](./02-concepts.md) page.

The server is **read-only**. No tool can register an Ontology Version, edit a Use Case, start or record a Construction Run, or move an Alias. The agent proposes a change to your pipeline; a person accepts it through a pull request.

## Register `stetiq mcp` with a coding agent

`stetiq mcp` needs the MCP Python SDK, the `mcp` extra. A clone set up as in [Getting started](./01-getting-started.md#install) has it already (`uv sync` installs it with the development tools); otherwise install it with `uv sync --extra mcp`. Without it, `stetiq mcp` exits 1 and says how to install it.

The server talks to the agent over stdio, so the agent starts it for you. It finds your tracking data like every other command: `--tracking-uri`, then `$STETIQ_TRACKING_URI`, then `sqlite:///.stetiq/stetiq.db` in the folder the agent starts it in (see [Tracking URI](./04-cli.md#tracking-uri)). In remote mode it sends `$STETIQ_TOKEN`, and a token with *read* permission is enough: giving an agent access never gives it edit rights.

With Claude Code, from your pipeline's repository:

```bash
claude mcp add stetiq --env STETIQ_TRACKING_URI=https://stetiq.example.com --env STETIQ_TOKEN=stq_3f9c1a2b_... -- stetiq mcp
```

With Cursor, add it to `.cursor/mcp.json` (Claude Code reads the same shape from `.mcp.json`):

```json
{
  "mcpServers": {
    "stetiq": {
      "command": "stetiq",
      "args": ["mcp"],
      "env": {"STETIQ_TRACKING_URI": "sqlite:////path/to/kg/stetiq.db"}
    }
  }
}
```

If `stetiq` is not on the agent's `PATH` (you installed it into a clone), give the full path to the clone's `.venv/bin/stetiq` as the command. Keep a real token out of files you commit: put it in the agent's local configuration instead.

## Tools

Each tool returns JSON, in the same form as the CLI and the REST API, so what the agent sees matches what you see.

| Tool | Arguments | What it returns |
| --- | --- | --- |
| `list_knowledge_graphs` | none | Every Knowledge Graph you can read, with a summary of its state, as `stetiq kg list` shows them. In remote mode, only those your API Token can read. |
| `run_context` | `knowledge_graph`, optional `version` | The [run context](./03-python-sdk.md#the-run-context), exactly as [`stetiq context`](./04-cli.md#the-run-context) prints it: the Ontology Version to extract against (the Contract Alias's, or `version`), the Use Case, how that version scores, and how runs against it were judged. Never instance data. |
| `ontology_diff` | `knowledge_graph`, `base`, `target` | The Ontology Diff from Ontology Version `base` to `target`, each change classed cosmetic, additive, deprecating or breaking, as the REST API's `GET /api/v1/knowledge-graphs/{name}/ontology-diff` returns it. |
| `consumer_impact` | `knowledge_graph`, `base`, `target` | Which Consumers, Tasks and Competency Questions of the latest Use Case Version that Ontology Diff hits, as `GET /api/v1/knowledge-graphs/{name}/consumer-impact` returns it. |

An error, such as an unknown Knowledge Graph or Ontology Version or a missing permission, comes back as a tool error carrying stetiq's message, so the agent can correct its call.

## The rules the agent is given

The server hands the agent its rules as MCP instructions, so it works within the loop stetiq is built for:

- **Extend the Ontology only where a Competency Question needs it.** If a change needs a question the Use Case does not have yet, the agent declares the question in the Use Case first. A Concept no Competency Question needs counts as an unjustified addition.
- **A Consumer Gate verdict names a symptom, not a cause.** A question that lost rows says what broke for a Consumer, not why; the cause is found in the Ontology Diff and the pipeline.
- **The agent proposes; a person accepts.** The agent's change goes into a pull request, where `stetiq gate` and [`stetiq consumer gate`](./04-cli.md#consumer-gates) judge it and a person decides.
