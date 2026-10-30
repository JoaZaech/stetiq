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
from stetiq.errors import EvaluatorError, StetiqError

app = typer.Typer(no_args_is_help=True, help="Version, evaluate and govern knowledge-graph ontologies.")
kg_app = typer.Typer(no_args_is_help=True, help="Knowledge Graphs.")
ontology_app = typer.Typer(no_args_is_help=True, help="Ontology Versions.")
app.add_typer(kg_app, name="kg")
app.add_typer(ontology_app, name="ontology")
alias_app = typer.Typer(no_args_is_help=True, help="Aliases, the Contract Alias and Promotion.")
app.add_typer(alias_app, name="alias")

TrackingUri = Annotated[
    str | None,
    typer.Option("--tracking-uri", envvar="STETIQ_TRACKING_URI", help="http(s)://<server> (remote) or sqlite:///<path> (local)"),
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
) -> None:
    """Run the self-hosted stetiq server; point clients at it with --tracking-uri http://HOST:PORT."""
    import uvicorn

    from stetiq.server import create_app

    uvicorn.run(create_app(database_url), host=host, port=port)


@kg_app.command("create")
def kg_create(
    name: str,
    ontology: Annotated[
        Path | None,
        typer.Option("--ontology", exists=True, dir_okay=False, help="Declared Ontology (stetiq YAML)"),
    ] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Create a Knowledge Graph with its initial Declared Ontology."""
    try:
        kg = _client(tracking_uri).create_knowledge_graph(name, ontology=ontology)
    except StetiqError as e:
        raise _fail(e) from None
    typer.echo(f"Created Knowledge Graph {kg.name} with Ontology Version 1")


@ontology_app.command("register")
def ontology_register(knowledge_graph: str, ontology: OntologyFile, tracking_uri: TrackingUri = None) -> None:
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
        typer.echo(f"{v.number:<8} {v.origin:<11} {v.content_hash[:12]:<13} {v.created_at.isoformat()}")


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
        typer.echo(f"{r.evaluator}: {metrics}")
        for d in r.details:
            metric = f" [{d.metric}]" if d.metric else ""
            typer.echo(f"  - {d.item}{metric}: {d.message}" if d.message else f"  - {d.item}{metric}")


@ontology_app.command("evaluations")
def ontology_evaluations(knowledge_graph: str, version: int, tracking_uri: TrackingUri = None) -> None:
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
    tracking_uri: TrackingUri = None,
) -> None:
    """Re-run the built-in (and any given custom) Evaluators on an Ontology Version."""
    try:
        client = _client(tracking_uri)
        for spec in evaluator or []:
            client.register_evaluator(_load_evaluator(spec))
        results = client.evaluate(knowledge_graph, version)
    except StetiqError as e:
        raise _fail(e) from None
    _echo_results(results)


@ontology_app.command("diff")
def ontology_diff(
    knowledge_graph: str,
    base: Annotated[int | None, typer.Argument(help="Default: the Contract Alias's version")] = None,
    target: Annotated[int | None, typer.Argument(help="Default: the latest version")] = None,
    tracking_uri: TrackingUri = None,
) -> None:
    """Show the Ontology Diff from version BASE to TARGET, each change additive, deprecating or breaking."""
    try:
        d = _client(tracking_uri).diff_ontology_versions(knowledge_graph, base, target)
    except StetiqError as e:
        raise _fail(e) from None
    if not d.changes:
        typer.echo(f"No changes between Ontology Versions {base or 'contract'} and {target or 'latest'}")
        return
    width = max(len(c.concept) for c in d.changes)
    for c in d.changes:
        typer.echo(f"{c.classification:<12} {c.kind:<11} {c.concept:<{width}}  {c.detail}")
    typer.echo(f"Overall: {d.classification}")


Actor = Annotated[
    str | None,
    typer.Option("--actor", envvar="STETIQ_ACTOR", help="Who the audit log records (default: OS user)"),
]


@alias_app.command("set")
def alias_set(
    knowledge_graph: str, alias: str, version: int, actor: Actor = None, tracking_uri: TrackingUri = None
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
    alias: Annotated[str | None, typer.Argument(help="Designate this Alias; omit to show the current one")] = None,
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
    typer.Option("--config", dir_okay=False, help="Repo config file declaring the Construction Entry Point"),
]


@app.command("run")
def run(
    knowledge_graph: Annotated[
        str | None, typer.Argument(help="Default: `knowledge_graph` from the repo config")
    ] = None,
    config: ConfigFile = Path(DEFAULT_CONFIG_PATH),
    ontology_version: Annotated[
        int | None, typer.Option("--ontology-version", help="Declared Ontology (default: the Contract Alias's version)")
    ] = None,
    alias: Annotated[str | None, typer.Option("--alias", help="Use the version this Alias points to")] = None,
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
        typer.echo("error: name the Knowledge Graph, or set knowledge_graph in the repo config", err=True)
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


# --- API tokens (ticket #17): admin commands, run against the server's database ----------

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
