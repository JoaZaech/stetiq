"""The stetiq CLI: a thin layer over the SDK."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Annotated

import typer
import yaml

from stetiq.client import Client
from stetiq.config import DEFAULT_CONFIG_PATH, load_config
from stetiq.entry_point import EntryPoint
from stetiq.errors import EvaluatorError, GateConfigError, StetiqError
from stetiq.gates import parse_gates
from stetiq.use_case import to_yaml as to_use_case_yaml

app = typer.Typer(
    no_args_is_help=True, help="Version, evaluate and govern knowledge-graph ontologies."
)
kg_app = typer.Typer(no_args_is_help=True, help="Knowledge Graphs.")
ontology_app = typer.Typer(no_args_is_help=True, help="Ontology Versions.")
app.add_typer(kg_app, name="kg")
app.add_typer(ontology_app, name="ontology")
use_case_app = typer.Typer(no_args_is_help=True, help="Use Cases (Competency Questions).")
app.add_typer(use_case_app, name="use-case")
alias_app = typer.Typer(no_args_is_help=True, help="Aliases, the Contract Alias and Promotion.")
app.add_typer(alias_app, name="alias")

TrackingUri = Annotated[
    str | None,
    typer.Option(
        "--tracking-uri",
        envvar="STETIQ_TRACKING_URI",
        help="http(s)://<server> (remote) or sqlite:///<path> (local)",
    ),
]
OntologyFile = Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="stetiq YAML file")]


def _client(tracking_uri: str | None) -> Client:
    return Client(tracking_uri)


def _fail(e: StetiqError) -> typer.Exit:
    typer.echo(f"error: {e}", err=True)
    return typer.Exit(code=1)


@app.command("server")
def server(
    database_url: Annotated[
        str | None,
        typer.Option(
            "--database-url",
            envvar="STETIQ_DATABASE_URL",
            help="sqlite:///<path> or postgresql+psycopg://user@host/db (default sqlite:///.stetiq/server.db)",
        ),
    ] = None,
    host: Annotated[str, typer.Option(help="Interface to bind")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on")] = 5000,
    question_mapper: Annotated[
        str | None,
        typer.Option(
            "--question-mapper",
            envvar="STETIQ_QUESTION_MAPPER",
            help="Maps Competency Questions without a query onto the Ontology: "
            "'anthropic' (Claude; needs stetiq[llm]), 'module:attr', or 'none' (default)",
        ),
    ] = None,
) -> None:
    """Run the self-hosted stetiq server; point clients at it with --tracking-uri http://HOST:PORT."""
    import uvicorn

    from stetiq.evaluation.llm_mapping import question_mapper_from_spec
    from stetiq.server import create_app

    try:
        mapper = question_mapper_from_spec(question_mapper)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--question-mapper") from None
    uvicorn.run(create_app(database_url, question_mapper=mapper), host=host, port=port)


@kg_app.command("create")
def kg_create(
    name: str,
    ontology: Annotated[
        Path | None,
        typer.Option(
            "--ontology", exists=True, dir_okay=False, help="Declared Ontology (stetiq YAML)"
        ),
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Create a Knowledge Graph with its initial Declared Ontology."""
    try:
        kg = _client(tracking_uri).create_knowledge_graph(name, ontology=ontology)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"Created Knowledge Graph {kg.name} with Ontology Version 1")


@kg_app.command("list")
def kg_list(tracking_uri: TrackingUri = None) -> None:
    """List Knowledge Graphs (in server mode: those the API token can read)."""
    try:
        kgs = _client(tracking_uri).list_knowledge_graphs()
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"{'NAME':<32} CREATED")
    for kg in kgs:
        typer.echo(f"{kg.name:<32} {kg.created_at.isoformat()}")


@kg_app.command("bind-source")
def kg_bind_source(
    knowledge_graph: str,
    database: Annotated[str, typer.Option("--database", help="Graph Source database")] = "neo4j",
    label: Annotated[
        str | None, typer.Option("--label", help="Only nodes carrying this label")
    ] = None,
    namespace: Annotated[
        str | None, typer.Option("--namespace", help="Only nodes in this namespace")
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Bind the Knowledge Graph to a Graph Source scope (replacing any earlier one)."""
    from stetiq.graph_source import GraphSourceScope

    scope = GraphSourceScope(database=database, label=label, namespace=namespace)
    try:
        _client(tracking_uri).bind_graph_source(knowledge_graph, scope)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"Bound {knowledge_graph} to {_scope_text(scope)}")


def _scope_text(scope) -> str:
    parts = [f"database={scope.database}"]
    if scope.label is not None:
        parts.append(f"label={scope.label}")
    if scope.namespace is not None:
        parts.append(f"namespace={scope.namespace}")
    return " ".join(parts)


@kg_app.command("source")
def kg_source(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """Show the Graph Source scope the Knowledge Graph is bound to."""
    try:
        scope = _client(tracking_uri).get_graph_source(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(_scope_text(scope))


@kg_app.command("evolution-mode")
def kg_evolution_mode(
    knowledge_graph: str,
    mode: Annotated[
        str | None, typer.Argument(help="strict or evolving; omit to show the current mode")
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Show or set the Evolution Mode: what a run introducing new Concepts does."""
    try:
        client = _client(tracking_uri)
        if mode is not None:
            client.set_evolution_mode(knowledge_graph, mode)  # type: ignore[arg-type]
        typer.echo(client.get_evolution_mode(knowledge_graph))
    except StetiqError as e:
        raise _fail(e) from None


@ontology_app.command("register")
def ontology_register(
    knowledge_graph: str, ontology: OntologyFile, tracking_uri: TrackingUri = None
) -> None:
    """Register an Ontology by hand; identical content returns the existing version."""
    try:
        version = _client(tracking_uri).register_ontology(knowledge_graph, ontology)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"Ontology Version {version.number} ({version.content_hash[:12]})")


@ontology_app.command("list")
def ontology_list(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """List a Knowledge Graph's Ontology Versions with their origin."""
    try:
        versions = _client(tracking_uri).list_ontology_versions(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"{'VERSION':<8} {'ORIGIN':<11} {'HASH':<13} CREATED")
    for v in versions:
        typer.echo(
            f"{v.number:<8} {v.origin:<11} {v.content_hash[:12]:<13} {v.created_at.isoformat()}"
        )


@ontology_app.command("get")
def ontology_get(knowledge_graph: str, version: int, tracking_uri: TrackingUri = None) -> None:
    """Print an Ontology Version as stetiq YAML."""
    try:
        text = _client(tracking_uri).get_ontology_yaml(knowledge_graph, version)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(text, nl=False)


def _load_evaluator(spec: str):
    """`module:attr`, where attr is an Evaluator class (instantiated) or instance."""
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise EvaluatorError(f"--evaluator {spec!r}: expected module:attribute")
    try:
        obj = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as e:
        raise EvaluatorError(f"--evaluator {spec!r}: {e}") from None
    return obj() if isinstance(obj, type) else obj


def _echo_results(results) -> None:
    for r in results:
        metrics = "  ".join(f"{k}={v:g}" for k, v in sorted(r.metrics.items()))
        against = "" if r.use_case_version is None else f" (Use Case version {r.use_case_version})"
        typer.echo(f"{r.evaluator}{against}: {metrics}")
        for d in r.details:
            metric = f" [{d.metric}]" if d.metric else ""
            typer.echo(
                f"  - {d.item}{metric}: {d.message}" if d.message else f"  - {d.item}{metric}"
            )


@ontology_app.command("evaluations")
def ontology_evaluations(
    knowledge_graph: str, version: int, tracking_uri: TrackingUri = None
) -> None:
    """Show the latest result of every Evaluator for an Ontology Version."""
    try:
        results = _client(tracking_uri).get_evaluation_results(knowledge_graph, version)
    except StetiqError as e:
        raise _fail(e) from None
    _echo_results(results)


@ontology_app.command("evaluate")
def ontology_evaluate(
    knowledge_graph: str,
    version: int,
    evaluator: Annotated[
        list[str] | None,
        typer.Option("--evaluator", help="Custom Evaluator as module:Class (repeatable)"),
    ] = None,
    use_case_version: Annotated[
        int | None,
        typer.Option(
            "--use-case-version",
            help="Judge answerability against this Use Case version (default latest)",
        ),
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Re-run the built-in (and any given custom) Evaluators on an Ontology Version."""
    try:
        client = _client(tracking_uri)
        for spec in evaluator or []:
            client.register_evaluator(_load_evaluator(spec))
        results = client.evaluate(knowledge_graph, version, use_case_version=use_case_version)
    except StetiqError as e:
        raise _fail(e) from None
    _echo_results(results)


@ontology_app.command("diff")
def ontology_diff(
    knowledge_graph: str,
    base: Annotated[
        int | None, typer.Argument(help="Default: the Contract Alias's version")
    ] = None,
    target: Annotated[
        int | None, typer.Argument(help="Default: the latest Candidate, else the latest version")
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Show the Ontology Diff from version BASE to TARGET, each change additive, deprecating or breaking."""
    try:
        d = _client(tracking_uri).diff_ontology_versions(knowledge_graph, base, target)
    except StetiqError as e:
        raise _fail(e) from None
    if not d.changes:
        typer.echo(
            f"No changes between Ontology Versions {base or 'contract'} and {target or 'latest Candidate'}"
        )
        return
    width = max(len(c.concept) for c in d.changes)
    for c in d.changes:
        typer.echo(f"{c.classification:<12} {c.kind:<11} {c.concept:<{width}}  {c.detail}")
    typer.echo(f"Overall: {d.classification}")


@use_case_app.command("register")
def use_case_register(
    knowledge_graph: str,
    use_case: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="Use Case YAML file")
    ],
    tracking_uri: TrackingUri = None,
) -> None:
    """Register the Knowledge Graph's Use Case as a new Use Case version."""
    try:
        version = _client(tracking_uri).register_use_case(knowledge_graph, use_case)
    except StetiqError as e:
        raise _fail(e) from None
    count = len(version.use_case.competency_questions)
    typer.echo(f"Use Case version {version.number} ({count} Competency Questions)")


@use_case_app.command("add-question")
def use_case_add_question(
    knowledge_graph: str,
    id: Annotated[str, typer.Option("--id", help="Stable id, unique within the Use Case")],
    question: Annotated[str, typer.Option("--question", help="The natural-language question")],
    query: Annotated[str | None, typer.Option("--query", help="Cypher query answering it")] = None,
    concept: Annotated[
        list[str] | None,
        typer.Option("--concept", help="Concept reference it needs (repeatable)"),
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Add a Competency Question to the latest Use Case, creating a new Use Case version."""
    from stetiq.use_case import CompetencyQuestion

    cq = CompetencyQuestion(id=id, question=question, query=query, concepts=tuple(concept or ()))
    try:
        version = _client(tracking_uri).add_competency_question(knowledge_graph, cq)
    except StetiqError as e:
        raise _fail(e) from None
    count = len(version.use_case.competency_questions)
    typer.echo(f"Use Case version {version.number} ({count} questions)")


@use_case_app.command("list")
def use_case_list(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """List a Knowledge Graph's Use Case versions."""
    try:
        versions = _client(tracking_uri).list_use_case_versions(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"{'VERSION':<8} {'QUESTIONS':<10} {'HASH':<13} CREATED")
    for v in versions:
        typer.echo(
            f"{v.number:<8} {len(v.use_case.competency_questions):<10} "
            f"{v.content_hash[:12]:<13} {v.created_at.isoformat()}"
        )


@use_case_app.command("get")
def use_case_get(knowledge_graph: str, version: int, tracking_uri: TrackingUri = None) -> None:
    """Print a Use Case version as YAML."""
    try:
        found = _client(tracking_uri).get_use_case_version(knowledge_graph, version)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(to_use_case_yaml(found.use_case), nl=False)


Actor = Annotated[
    str | None,
    typer.Option(
        "--actor", envvar="STETIQ_ACTOR", help="Who the audit log records (default: OS user)"
    ),
]


@alias_app.command("set")
def alias_set(
    knowledge_graph: str,
    alias: str,
    version: int,
    actor: Actor = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Create ALIAS or move it to VERSION (Promotion, or rollback to an earlier version)."""
    try:
        moved = Client(tracking_uri, actor=actor).set_alias(knowledge_graph, alias, version)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"Alias {moved.name} -> Ontology Version {moved.version}")


@alias_app.command("list")
def alias_list(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """List a Knowledge Graph's Aliases; the Contract Alias is marked."""
    try:
        client = _client(tracking_uri)
        aliases = client.list_aliases(knowledge_graph)
        contract = client.get_contract_alias(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    width = max([5, *(len(a.name) for a in aliases)])
    typer.echo(f"{'ALIAS':<{width}} {'VERSION':<8} {'UPDATED':<33} CONTRACT")
    for a in aliases:
        mark = "*" if a.name == contract else ""
        typer.echo(f"{a.name:<{width}} {a.version:<8} {a.updated_at.isoformat():<33} {mark}")


@alias_app.command("get")
def alias_get(knowledge_graph: str, alias: str, tracking_uri: TrackingUri = None) -> None:
    """Print the Ontology Version ALIAS points to as stetiq YAML."""
    try:
        version = _client(tracking_uri).get_ontology_version_by_alias(knowledge_graph, alias)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(version.to_yaml(), nl=False)


@alias_app.command("log")
def alias_log(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """Show the audit log of Alias moves, oldest first."""
    try:
        promotions = _client(tracking_uri).list_promotions(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    width = max([5, *(len(p.alias) for p in promotions)])
    typer.echo(f"{'ALIAS':<{width}} {'FROM':<5} {'TO':<5} {'ACTOR':<16} {'GATE':<5} TIME")
    for p in promotions:
        from_version = "-" if p.from_version is None else str(p.from_version)
        gate = p.gate_result or "-"
        typer.echo(
            f"{p.alias:<{width}} {from_version:<5} {p.to_version:<5} {p.actor:<16} {gate:<5} "
            f"{p.promoted_at.isoformat()}"
        )


@alias_app.command("contract")
def alias_contract(
    knowledge_graph: str,
    alias: Annotated[
        str | None, typer.Argument(help="Designate this Alias; omit to show the current one")
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Show the Contract Alias, or designate ALIAS as the Contract Alias."""
    try:
        client = _client(tracking_uri)
        if alias is not None:
            client.set_contract_alias(knowledge_graph, alias)
        typer.echo(client.get_contract_alias(knowledge_graph))
    except StetiqError as e:
        raise _fail(e) from None


ConfigFile = Annotated[
    Path,
    typer.Option(
        "--config", dir_okay=False, help="Repo config file declaring the Construction Entry Point"
    ),
]


@app.command("run")
def run(
    knowledge_graph: Annotated[
        str | None, typer.Argument(help="Default: `knowledge_graph` from the repo config")
    ] = None,
    config: ConfigFile = Path(DEFAULT_CONFIG_PATH),
    ontology_version: Annotated[
        int | None,
        typer.Option(
            "--ontology-version", help="Declared Ontology (default: the Contract Alias's version)"
        ),
    ] = None,
    alias: Annotated[
        str | None, typer.Option("--alias", help="Use the version this Alias points to")
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Invoke the Construction Entry Point as a Construction Run, then observe the Graph Source.

    The command runs from the config file's directory. Exits non-zero when the run
    fails: the entry point exited non-zero, or strict Evolution Mode saw new Concepts."""
    try:
        settings = load_config(config)
        entry_point = EntryPoint.from_config(settings)
    except (OSError, ValueError, yaml.YAMLError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from None
    knowledge_graph = knowledge_graph or settings.get("knowledge_graph")
    if not knowledge_graph:
        typer.echo(
            "error: name the Knowledge Graph, or set knowledge_graph in the repo config", err=True
        )
        raise typer.Exit(code=1)
    try:
        result = _client(tracking_uri).run_entry_point(
            knowledge_graph,
            entry_point,
            ontology_version=ontology_version,
            alias=alias,
            cwd=config.resolve().parent,
        )
    except (StetiqError, ValueError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from None
    _echo_run(result)
    if result.status != "finished":
        raise typer.Exit(code=1)


def _echo_run(run) -> None:
    typer.echo(f"Construction Run {run.id} {run.status} (Ontology Version {run.ontology_version})")
    exit_code = run.params.get("entry_point.exit_code")
    if exit_code not in (None, "0"):
        typer.echo(f"  entry point exited with code {exit_code}")
    if run.conformance is not None:
        typer.echo(f"  Conformance: {run.conformance.score:.3f}")
        if run.status == "failed":
            new = ", ".join(m.subject for m in run.conformance.undeclared)
            typer.echo(f"  strict Evolution Mode: new Concepts observed: {new}")
    if run.candidate_version is not None:
        typer.echo(f"  Candidate: Ontology Version {run.candidate_version}")


# --- API tokens: admin commands, run against the server's database ----------

token_app = typer.Typer(
    no_args_is_help=True,
    help="API tokens for server mode (admin: talks to the server's database directly).",
)
app.add_typer(token_app, name="token")

DatabaseUrl = Annotated[
    str | None,
    typer.Option(
        "--database-url",
        envvar="STETIQ_DATABASE_URL",
        help="The stetiq server's database (default sqlite:///.stetiq/server.db)",
    ),
]


def _token_registry(database_url: str | None):
    from stetiq.auth import TokenRegistry
    from stetiq.server import DEFAULT_DATABASE_URL

    return TokenRegistry(database_url or DEFAULT_DATABASE_URL)


def _grants_text(grants) -> str:
    return ",".join(f"{kg}={permission}" for kg, permission in sorted(grants.items()))


@token_app.command("create")
def token_create(
    user: Annotated[str, typer.Argument(help="Recorded as actor in the audit log")],
    grant: Annotated[
        list[str],
        typer.Option("--grant", help="KNOWLEDGE_GRAPH=read|edit (repeatable; `*` = every KG)"),
    ],
    database_url: DatabaseUrl = None,
) -> None:
    """Issue an API token for USER; the token is printed once (last line of output)."""
    grants: dict[str, str] = {}
    for g in grant:
        kg, sep, permission = g.rpartition("=")
        if not sep:
            raise _fail(StetiqError(f"Grant {g!r}: expected KNOWLEDGE_GRAPH=read|edit"))
        grants[kg] = permission
    try:
        token, value = _token_registry(database_url).issue(user, grants)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"Created token {token.id} for {token.user} ({_grants_text(token.grants)}):")
    typer.echo(value)


@token_app.command("list")
def token_list(database_url: DatabaseUrl = None) -> None:
    """List API tokens (never their secrets)."""
    tokens = _token_registry(database_url).list()
    typer.echo(f"{'ID':<9} {'USER':<16} {'STATUS':<8} GRANTS")
    for t in tokens:
        status = "revoked" if t.revoked_at else "active"
        typer.echo(f"{t.id:<9} {t.user:<16} {status:<8} {_grants_text(t.grants)}")


@token_app.command("revoke")
def token_revoke(token_id: str, database_url: DatabaseUrl = None) -> None:
    """Revoke the API token TOKEN_ID; requests using it are rejected from now on."""
    try:
        _token_registry(database_url).revoke(token_id)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"Revoked token {token_id}")


# --- On-demand Observation and Drift ----------------------------------------------------

drift_app = typer.Typer(no_args_is_help=True, help="Drift events.")
app.add_typer(drift_app, name="drift")

# `stetiq observe` exits with this code when the Observation raised Drift (errors exit 1),
# so a scheduler can tell "the graph drifted" from "the check could not run".
DRIFT_EXIT_CODE = 3
DEFAULT_CONFIG = Path(DEFAULT_CONFIG_PATH)

ConfigPath = Annotated[
    Path | None,
    typer.Option(
        "--config", dir_okay=False, help="Repo config file (default ./stetiq.yaml, if present)"
    ),
]


def _repo_config(path: Path | None) -> dict:
    """The repo config; a missing default ./stetiq.yaml means an empty config."""
    if path is None:
        return load_config(DEFAULT_CONFIG) if DEFAULT_CONFIG.is_file() else {}
    if not path.is_file():
        raise StetiqError(f"config file {path} does not exist")
    try:
        return load_config(path)
    except (ValueError, yaml.YAMLError) as e:
        raise StetiqError(f"{path}: {e}") from None


def _echo_findings(findings) -> None:
    for f in findings:
        typer.echo(f"  {f.kind:<15} {f.subject_kind:<18} {f.subject}  {f.detail}".rstrip())


@app.command("observe")
def observe(
    knowledge_graph: Annotated[
        str | None, typer.Argument(help="Default: `knowledge_graph` from the repo config")
    ] = None,
    config: ConfigPath = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Observe the Knowledge Graph's Graph Source now and check it for Drift.

    Compares the Observed Schema with the Contract Alias's Ontology Version and the
    previous Observation (thresholds from the `drift:` section of the repo config).
    Exits 3 on Drift, 1 on errors. Schedule it with your own cron, Airflow or CI."""
    from stetiq.drift import thresholds_from_config

    try:
        settings = _repo_config(config)
        thresholds = thresholds_from_config(settings)
        kg = knowledge_graph or settings.get("knowledge_graph")
        if not kg:
            raise StetiqError(
                "no Knowledge Graph given (argument or `knowledge_graph` in the repo config)"
            )
        outcome = _client(tracking_uri).observe(kg, thresholds=thresholds)
    except StetiqError as e:
        raise _fail(e) from None
    obs = outcome.observation
    typer.echo(f"Observation {obs.id} of {kg} at {obs.observed_at.isoformat()}")
    if outcome.drift is None:
        typer.echo("No Drift")
        return
    d = outcome.drift
    typer.echo(
        f"Drift: {len(d.findings)} finding(s) against {d.contract_alias} "
        f"(Ontology Version {d.ontology_version})"
    )
    _echo_findings(d.findings)
    raise typer.Exit(code=DRIFT_EXIT_CODE)


@drift_app.command("list")
def drift_list(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """List a Knowledge Graph's Drift events, oldest first."""
    try:
        events = _client(tracking_uri).list_drift_events(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"{'DETECTED':<33} {'CONTRACT':<16} {'STRUCT':<7} {'STATS':<6} OBSERVATION")
    for e in events:
        contract = f"{e.contract_alias}@{e.ontology_version}"
        typer.echo(
            f"{e.detected_at.isoformat():<33} {contract:<16} {len(e.structural):<7} "
            f"{len(e.statistical):<6} {e.observation_id}"
        )


# Like `stetiq observe`'s Drift code: a finding, distinct from 1 = error and 2 = usage error.
GATE_FAILED_EXIT_CODE = 3


@app.command("gate")
def gate(
    knowledge_graph: Annotated[
        str | None, typer.Argument(help="Default: knowledge_graph from the config file")
    ] = None,
    version: Annotated[
        int | None, typer.Option("--version", help="Ontology Version to gate (default: the latest)")
    ] = None,
    run: Annotated[str | None, typer.Option("--run", help="Construction Run id to gate")] = None,
    config: Annotated[
        Path, typer.Option("--config", help="Repo config file holding the Gates")
    ] = Path(DEFAULT_CONFIG_PATH),
    tracking_uri: TrackingUri = None,
) -> None:
    """Evaluate the config file's Gates for an Ontology Version or a run; record the result
    on the server. Exit codes: 0 all Gates passed, 3 a Gate failed, 1 error (bad config...)."""
    try:
        if version is not None and run is not None:
            raise GateConfigError("give --version or --run, not both")
        try:
            settings = load_config(config)
        except (OSError, ValueError, yaml.YAMLError) as e:
            raise GateConfigError(f"Cannot read config file {config}: {e}") from None
        knowledge_graph = knowledge_graph or settings.get("knowledge_graph")
        if not knowledge_graph:
            raise GateConfigError(f"No Knowledge Graph given and none set in {config}")
        gates = parse_gates(settings.get("gates"))
        if not gates:
            raise GateConfigError(f"{config} defines no Gates")
        result = _client(tracking_uri).evaluate_gates(
            knowledge_graph, gates, version=version, run=run
        )
    except StetiqError as e:
        raise _fail(e) from None
    for outcome in result.outcomes:
        typer.echo(f"{'PASS' if outcome.passed else 'FAIL'}  {outcome.gate.name}")
        if not outcome.passed:
            for reason in outcome.reasons:
                typer.echo(f"      - {reason}")
    subject = f"run {run}" if run is not None else f"Ontology Version {result.ontology_version}"
    if result.passed:
        typer.echo(f"All {len(result.outcomes)} Gates passed for {knowledge_graph} {subject}")
        return
    typer.echo(
        f"{len(result.failed)} of {len(result.outcomes)} Gates failed for {knowledge_graph} {subject}"
    )
    raise typer.Exit(code=GATE_FAILED_EXIT_CODE)


@app.command("gate-results")
def gate_results(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """List every recorded Gate evaluation of the Knowledge Graph, oldest first."""
    try:
        results = _client(tracking_uri).list_gate_results(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    for r in results:
        subject = f"run {r.subject_id}" if r.subject_kind == "construction_run" else "version"
        verdict = "PASS" if r.passed else "FAIL"
        typer.echo(
            f"{r.evaluated_at.isoformat()}  {verdict}  Ontology Version {r.ontology_version} ({subject})"
        )
        for outcome in r.outcomes:
            typer.echo(f"  {'PASS' if outcome.passed else 'FAIL'}  {outcome.gate.name}")


# --- Construction Runs and Observations -------------------------------------------------

runs_app = typer.Typer(no_args_is_help=True, help="Construction Runs and their evaluation.")
app.add_typer(runs_app, name="runs")
observations_app = typer.Typer(no_args_is_help=True, help="Observations of the Graph Source.")
app.add_typer(observations_app, name="observations")


@runs_app.command("list")
def runs_list(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """List a Knowledge Graph's Construction Runs, oldest first."""
    try:
        runs = _client(tracking_uri).list_runs(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"{'ID':<33} {'STATUS':<9} {'VERSION':<8} {'CANDIDATE':<10} STARTED")
    for r in runs:
        candidate = "-" if r.candidate_version is None else str(r.candidate_version)
        typer.echo(
            f"{r.id:<33} {r.status:<9} {r.ontology_version:<8} {candidate:<10} "
            f"{r.started_at.isoformat()}"
        )


@runs_app.command("get")
def runs_get(run_id: str, tracking_uri: TrackingUri = None) -> None:
    """Show a Construction Run with its params and metrics."""
    try:
        found = _client(tracking_uri).get_run(run_id)
    except StetiqError as e:
        raise _fail(e) from None
    _echo_run(found)
    for key, value in sorted(found.params.items()):
        typer.echo(f"  param  {key} = {value}")
    for key, value in sorted(found.metrics.items()):
        typer.echo(f"  metric {key} = {value:g}")


@runs_app.command("compare")
def runs_compare(run_ids: list[str], tracking_uri: TrackingUri = None) -> None:
    """Compare Construction Runs side by side: params, metrics, Conformance and
    run-level Evaluator results."""
    try:
        cmp = _client(tracking_uri).compare_runs(run_ids)
    except StetiqError as e:
        raise _fail(e) from None

    def cell(value) -> str:
        if value is None:
            return "-"
        return f"{value:g}" if isinstance(value, float) else str(value)

    rows = [("run", tuple(r.id[:12] for r in cmp.runs))]
    rows.append(("ontology_version", cmp.ontology_versions))
    rows += [(f"param {k}", v) for k, v in cmp.params.items()]
    rows += [(f"metric {k}", v) for k, v in cmp.metrics.items()]
    rows.append(("conformance", tuple(None if c is None else c.score for c in cmp.conformance)))
    rows += list(cmp.evaluations.items())
    width = max(len(name) for name, _ in rows)
    for name, values in rows:
        typer.echo(f"{name:<{width}}  " + "  ".join(f"{cell(v):<14}" for v in values).rstrip())


@runs_app.command("evaluate")
def runs_evaluate(
    run_id: str,
    evaluator: Annotated[
        list[str] | None,
        typer.Option("--evaluator", help="Custom run Evaluator as module:Class (repeatable)"),
    ] = None,
    use_case_version: Annotated[
        int | None,
        typer.Option(
            "--use-case-version", help="Execute this Use Case version's questions (default latest)"
        ),
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Re-run run-level evaluation on a Construction Run that has an Observation."""
    try:
        extra = [_load_evaluator(spec) for spec in evaluator or []]
        results = _client(tracking_uri).evaluate_run(
            run_id, evaluators=extra, use_case_version=use_case_version
        )
    except StetiqError as e:
        raise _fail(e) from None
    _echo_results(results)


@runs_app.command("evaluations")
def runs_evaluations(run_id: str, tracking_uri: TrackingUri = None) -> None:
    """Show the latest result of every run-level Evaluator for a Construction Run."""
    try:
        results = _client(tracking_uri).get_run_evaluation_results(run_id)
    except StetiqError as e:
        raise _fail(e) from None
    _echo_results(results)


@observations_app.command("list")
def observations_list(knowledge_graph: str, tracking_uri: TrackingUri = None) -> None:
    """List the Knowledge Graph's Observations, oldest first (RUN is - for on-demand ones)."""
    try:
        observations = _client(tracking_uri).list_observations(knowledge_graph)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"{'ID':<33} {'OBSERVED':<33} {'NODES':<6} {'RELS':<6} RUN")
    for o in observations:
        typer.echo(
            f"{o.id:<33} {o.observed_at.isoformat():<33} {len(o.schema.node_types):<6} "
            f"{len(o.schema.relationship_types):<6} {o.run_id or '-'}"
        )
