"""The stetiq CLI: a thin layer over the SDK."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Annotated

import typer

from stetiq.client import Client
from stetiq.errors import EvaluatorError, StetiqError
from stetiq.use_case import to_yaml as to_use_case_yaml

app = typer.Typer(no_args_is_help=True, help="Version, evaluate and govern knowledge-graph ontologies.")
kg_app = typer.Typer(no_args_is_help=True, help="Knowledge Graphs.")
ontology_app = typer.Typer(no_args_is_help=True, help="Ontology Versions.")
app.add_typer(kg_app, name="kg")
app.add_typer(ontology_app, name="ontology")
use_case_app = typer.Typer(no_args_is_help=True, help="Use Cases (Competency Questions).")
app.add_typer(use_case_app, name="use-case")

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
        against = "" if r.use_case_version is None else f" (Use Case version {r.use_case_version})"
        typer.echo(f"{r.evaluator}{against}: {metrics}")
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
    use_case_version: Annotated[
        int | None,
        typer.Option("--use-case-version", help="Judge answerability against this Use Case version (default latest)"),
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
def ontology_diff(knowledge_graph: str, base: int, target: int, tracking_uri: TrackingUri = None) -> None:
    """Show the Ontology Diff from version BASE to TARGET, each change additive, deprecating or breaking."""
    try:
        d = _client(tracking_uri).diff_ontology_versions(knowledge_graph, base, target)
    except StetiqError as e:
        raise _fail(e) from None
    if not d.changes:
        typer.echo(f"No changes between Ontology Versions {base} and {target}")
        return
    width = max(len(c.concept) for c in d.changes)
    for c in d.changes:
        typer.echo(f"{c.classification:<12} {c.kind:<11} {c.concept:<{width}}  {c.detail}")
    typer.echo(f"Overall: {d.classification}")


@use_case_app.command("register")
def use_case_register(
    knowledge_graph: str,
    use_case: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Use Case YAML file")],
    tracking_uri: TrackingUri = None,
) -> None:
    """Register the Knowledge Graph's Use Case as a new Use Case version."""
    try:
        version = _client(tracking_uri).register_use_case(knowledge_graph, use_case)
    except StetiqError as e:
        raise _fail(e) from None
    count = len(version.use_case.competency_questions)
    typer.echo(f"Use Case version {version.number} ({count} Competency Questions)")


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
