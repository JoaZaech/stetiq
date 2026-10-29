"""The stetiq CLI: a thin layer over the SDK."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from stetiq.client import Client
from stetiq.errors import StetiqError

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
