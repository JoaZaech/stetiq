# CLI

The `stetiq` command does from a shell, a CI job or a scheduler what the [Python SDK](./03-python-sdk.md) does from code. It is a thin layer over the SDK: the same tracking URI, the same modes, the same results. The words used here are explained on the [Concepts](./02-concepts.md) page.

Every command has `--help`:

```bash
stetiq --help
stetiq kg --help
stetiq kg create --help
```

## Tracking URI

Every command that reads or changes tracked data takes `--tracking-uri`. Without it, the command uses `$STETIQ_TRACKING_URI`, and without that the local database `sqlite:///.stetiq/stetiq.db` in the current folder.

```bash
stetiq kg list --tracking-uri sqlite:///kg/stetiq.db
STETIQ_TRACKING_URI=https://stetiq.example.com stetiq kg list
```

A `sqlite:///` or `postgresql://` URI is local mode: the command works directly on that database. An `http(s)://` URI is remote mode: the command sends its requests to that stetiq server.

### API Token

In remote mode, every request needs an API Token. The CLI reads it only from `$STETIQ_TOKEN`: there is no `--token` flag, so the token never shows up in your shell history or in the process list.

```bash
export STETIQ_TRACKING_URI=https://stetiq.example.com
export STETIQ_TOKEN=stq_3f9c1a2b_...
stetiq kg list
```

Local mode needs no token. How to issue one is described in [Server & API Tokens](./05-server-and-api-tokens.md#issue-api-tokens).

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | An error, printed as `error: …` (unknown Knowledge Graph, missing permission, bad config file…). `stetiq run` also exits 1 when the Construction Run failed. |
| `2` | A usage error: an unknown command or option, or a missing argument. |
| `3` | A finding: `stetiq observe` found Drift, or `stetiq gate` had a Gate fail. |

## Commands

| Command | What it covers |
| --- | --- |
| `stetiq kg` | Knowledge Graphs, their Graph Source, Evolution Mode and description. |
| `stetiq ontology` | Ontology Versions: register, read, diff and evaluate them. |
| `stetiq use-case` | The Use Case and its Competency Questions. |
| `stetiq alias` | Aliases, the Contract Alias, Promotion and its audit log. |
| `stetiq run` | Start the Construction Entry Point as a Construction Run. |
| `stetiq runs` | Construction Runs: list, show, compare and evaluate them. |
| `stetiq observe` | Take an Observation now and check it for Drift. |
| `stetiq observations`, `stetiq drift` | List Observations and Drift events. |
| `stetiq gate`, `stetiq gate-results` | Evaluate the Gates in `stetiq.yaml`, and list past results. |
| `stetiq ui` | The web UI over a local tracking database. |
| `stetiq server` | The stetiq server. |
| `stetiq token` | Issue, list and revoke API Tokens (on the server's database). |

### Knowledge Graphs

```bash
stetiq kg create support --ontology support.yaml
stetiq kg list
stetiq kg bind-source support --database neo4j --label Support
stetiq kg source support
stetiq kg evolution-mode support strict
stetiq kg description support "Tickets and the customers who **opened** them."
```

- `kg create` registers the Declared Ontology (a stetiq YAML file) as Ontology Version 1.
- `kg list` shows, in remote mode, only the Knowledge Graphs your API Token can read.
- `kg bind-source` binds the Knowledge Graph to its Graph Source: a `--database`, optionally narrowed with `--label` or `--namespace`. It replaces any earlier binding. `kg source` shows it.
- `kg evolution-mode` shows the Evolution Mode, or sets it to `strict` or `evolving`. `kg description` shows the markdown description, or sets it (an empty string clears it).

### Ontology Versions

```bash
stetiq ontology register support support-v2.yaml
stetiq ontology list support
stetiq ontology get support 2
stetiq ontology diff support 1 2
stetiq ontology evaluate support 2 --evaluator my_checks:Documented
stetiq ontology evaluations support 2
```

- `ontology register` registers a changed Ontology. Content identical to an existing version returns that version.
- `ontology get` prints a version as stetiq YAML.
- `ontology diff KG BASE TARGET` prints the Ontology Diff, one change per line, each additive, deprecating or breaking, then the overall classification. Without `BASE` it starts from the Contract Alias's version; without `TARGET` it ends at the latest Candidate.
- `ontology evaluate` runs the built-in Evaluators again, plus any custom one given as `--evaluator module:Class` (repeatable; see [Custom Evaluators](./03-python-sdk.md#custom-evaluators)). `--use-case-version` picks the Use Case Version to judge answerability against. `ontology evaluations` shows the latest results.

### Use Cases

```bash
stetiq use-case register support use-case.yaml
stetiq use-case add-question support --id open-tickets --question "Which tickets are open?" --concept Ticket
stetiq use-case list support
stetiq use-case get support 2
```

Each change registers a new Use Case Version. `add-question` takes `--query` for a Cypher query that answers the question, and `--concept` (repeatable) for the Concepts it needs.

### Aliases and Promotion

```bash
stetiq alias set support production 3
stetiq alias list support
stetiq alias get support production
stetiq alias contract support production
stetiq alias log support
```

- `alias set KG ALIAS VERSION` creates the Alias or moves it: a Promotion, or a rollback to an earlier version. In local mode the audit log records `--actor`, else `$STETIQ_ACTOR`, else your OS user; in remote mode it records the API Token's user.
- `alias list` marks the Contract Alias with `*`. `alias contract` shows it, or designates another existing Alias.
- `alias get` prints the version an Alias points to as stetiq YAML, for a pipeline that needs the current contract.
- `alias log` is the Promotion audit log, with the Gate result each version had when it was promoted.

### Construction Runs

```bash
stetiq run
stetiq run support --alias staging
stetiq runs list support
stetiq runs get 5d0c1f2e9a7b4c3d8e6f1a2b3c4d5e6f
stetiq runs compare 5d0c1f2e9a7b4c3d8e6f1a2b3c4d5e6f 81a4c0e2f3b5d6e7f8a9b0c1d2e3f4a5
stetiq runs evaluate 5d0c1f2e9a7b4c3d8e6f1a2b3c4d5e6f --evaluator my_checks:EdgeDensity
stetiq runs evaluations 5d0c1f2e9a7b4c3d8e6f1a2b3c4d5e6f
```

`stetiq run` starts the Construction Entry Point declared in [`stetiq.yaml`](./06-stetiq-yaml.md) as a Construction Run, from the config file's folder (choose the file with `--config`). It consumes the Contract Alias's version unless you pass `--ontology-version` or `--alias`, and the Knowledge Graph defaults to `knowledge_graph` in the config file. When the command exits 0, stetiq observes the Graph Source, measures Conformance and applies the Evolution Mode. `stetiq run` exits 1 when the run failed: the command exited non-zero, or a *strict* Evolution Mode saw new Concepts.

`runs evaluate` runs run-level evaluation again (Conformance, Observed Schema statistics, executed Competency Questions and any `--evaluator`) on a run that reached its Observation.

Observing needs your Graph Source credentials, so `stetiq run`, `stetiq observe` and `stetiq runs evaluate` read them from `$STETIQ_GRAPH_SOURCE_URI`, `$STETIQ_GRAPH_SOURCE_USER` and `$STETIQ_GRAPH_SOURCE_PASSWORD` (see [Graph Source](./03-python-sdk.md#graph-source)). They stay on the machine running the command.

### Observations and Drift

```bash
stetiq observe support
stetiq observations list support
stetiq drift list support
```

`stetiq observe` takes an Observation now, outside any Construction Run, and compares it with the Contract Alias's version and with the previous Observation. Drift thresholds come from the `drift:` section of `stetiq.yaml` (or `--config`). It exits 3 when it found Drift and 1 when the check could not run, so a cron job, Airflow task or CI step can tell the two apart.

### Gates

```bash
stetiq gate support --version 3
stetiq gate --run 5d0c1f2e9a7b4c3d8e6f1a2b3c4d5e6f
stetiq gate-results support
```

`stetiq gate` evaluates the Gates in `stetiq.yaml` (or `--config`) for an Ontology Version (default: the latest) or a Construction Run, and records the result. It prints `PASS` or `FAIL` per Gate with the reasons, and exits 3 if a Gate failed, so it fits a CI check. `gate-results` lists every recorded evaluation.

### Web UI, server and API Tokens

```bash
stetiq ui --port 5000
stetiq server --database-url postgresql+psycopg://stetiq@db.example.com/stetiq
stetiq token create ada --grant support=edit
stetiq token list
stetiq token revoke 3f9c1a2b
```

- `stetiq ui` serves the web UI over a local tracking database, with no API Token (see [Getting started](./01-getting-started.md#open-the-web-ui)). It refuses an `http(s)://` tracking URI, and a `--host` other than a loopback address unless you pass `--no-auth`.
- `stetiq server` and `stetiq token` are covered in [Server & API Tokens](./05-server-and-api-tokens.md). The `token` commands work on the server's database (`--database-url` or `$STETIQ_DATABASE_URL`), not over HTTP, and take no tracking URI.
