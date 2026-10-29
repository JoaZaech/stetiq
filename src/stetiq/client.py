"""The public Python SDK."""

from __future__ import annotations

import os
from pathlib import Path

from stetiq.errors import GraphSourceUnavailableError
from stetiq.graph_source import GraphSource, GraphSourceScope
from stetiq.ontology import Ontology, parse_yaml
from stetiq.tracking import (
    ConstructionRun,
    KnowledgeGraph,
    LocalTrackingService,
    Observation,
    OntologyVersion,
    RunComparison,
    RemoteTrackingService,
    SqlStore,
    TrackingService,
)

TRACKING_URI_ENV = "STETIQ_TRACKING_URI"
DEFAULT_TRACKING_URI = "sqlite:///.stetiq/stetiq.db"

# A Declared Ontology given to the SDK: stetiq YAML text, a path to a YAML file,
# or an already-built Ontology model.
OntologyInput = str | os.PathLike[str] | Ontology


def resolve_tracking_uri(tracking_uri: str | None = None) -> str:
    return tracking_uri or os.environ.get(TRACKING_URI_ENV) or DEFAULT_TRACKING_URI


def service_for_uri(tracking_uri: str) -> TrackingService:
    """Pick the mode from the tracking URI.

    - `http://` / `https://`: remote mode, talking to a stetiq server
    - `sqlite:///<path>`, `postgresql[+psycopg]://...`: local mode, in-process over that database
    """
    scheme = tracking_uri.split(":", 1)[0].lower()
    if scheme in ("http", "https"):
        return RemoteTrackingService(tracking_uri)
    if scheme == "sqlite" or scheme.startswith("postgresql"):
        return LocalTrackingService(SqlStore(tracking_uri))
    raise ValueError(
        f"Unsupported tracking URI {tracking_uri!r} "
        "(expected http(s)://<server>, sqlite:///<path> or postgresql://...)"
    )


def _to_ontology(ontology: OntologyInput) -> Ontology:
    if isinstance(ontology, Ontology):
        return ontology
    if isinstance(ontology, os.PathLike):
        return parse_yaml(Path(ontology).read_text(encoding="utf-8"))
    return parse_yaml(ontology)


class Client:
    """Entry point to stetiq: remote mode for `http(s)://` tracking URIs, else local mode."""

    def __init__(
        self,
        tracking_uri: str | None = None,
        *,
        service: TrackingService | None = None,
        graph_source: GraphSource | None = None,
    ) -> None:
        """`graph_source` is the adapter (e.g. Neo4j, with its credentials) used to observe
        the bound Graph Source scope when a Construction Run ends. It runs in this
        process: the stetiq server never connects to the graph database."""
        self.tracking_uri = resolve_tracking_uri(tracking_uri)
        self._service = service or service_for_uri(self.tracking_uri)
        self._graph_source = graph_source

    def create_knowledge_graph(
        self, name: str, ontology: OntologyInput | None = None
    ) -> KnowledgeGraph:
        """Create a Knowledge Graph; its Declared Ontology becomes Ontology Version 1."""
        declared = None if ontology is None else _to_ontology(ontology)
        return self._service.create_knowledge_graph(name, declared)

    def get_knowledge_graph(self, name: str) -> KnowledgeGraph:
        return self._service.get_knowledge_graph(name)

    def register_ontology(self, knowledge_graph: str, ontology: OntologyInput) -> OntologyVersion:
        """Register an Ontology by hand; identical content returns the existing version."""
        return self._service.register_ontology(knowledge_graph, _to_ontology(ontology))

    def list_ontology_versions(self, knowledge_graph: str) -> list[OntologyVersion]:
        return self._service.list_ontology_versions(knowledge_graph)

    def get_ontology_version(self, knowledge_graph: str, number: int) -> OntologyVersion:
        return self._service.get_ontology_version(knowledge_graph, number)

    def get_ontology_yaml(self, knowledge_graph: str, number: int) -> str:
        return self.get_ontology_version(knowledge_graph, number).to_yaml()

    # --- Graph Sources --------------------------------------------------------------

    def bind_graph_source(self, knowledge_graph: str, scope: GraphSourceScope) -> None:
        """Bind the Knowledge Graph to a Graph Source scope (replacing any earlier one)."""
        self._service.bind_graph_source(knowledge_graph, scope)

    def get_graph_source(self, knowledge_graph: str) -> GraphSourceScope:
        return self._service.get_graph_source(knowledge_graph)

    # --- Construction Runs ----------------------------------------------------------

    def start_run(self, knowledge_graph: str, *, ontology_version: int) -> ActiveRun:
        """Start a Construction Run consuming `ontology_version` as its Declared Ontology.

        Use the result as a context manager: leaving the block ends the run (which
        observes the Graph Source); an exception inside it marks the run failed."""
        if self._graph_source is None:
            raise GraphSourceUnavailableError(
                "Client has no Graph Source adapter to observe with; pass graph_source=..."
            )
        run = self._service.start_run(knowledge_graph, ontology_version)
        declared = self._service.get_ontology_version(knowledge_graph, ontology_version)
        return ActiveRun(self._service, self._graph_source, run, declared.ontology)

    def get_run(self, run_id: str) -> ConstructionRun:
        return self._service.get_run(run_id)

    def list_runs(self, knowledge_graph: str) -> list[ConstructionRun]:
        """All Construction Runs of the Knowledge Graph, oldest first."""
        return self._service.list_runs(knowledge_graph)

    def compare_runs(self, run_ids: list[str]) -> RunComparison:
        """Runs side by side: their params, metrics and consumed Ontology Versions."""
        runs = tuple(self.get_run(i) for i in run_ids)
        param_keys = sorted({k for r in runs for k in r.params})
        metric_keys = sorted({k for r in runs for k in r.metrics})
        return RunComparison(
            runs=runs,
            params={k: tuple(r.params.get(k) for r in runs) for k in param_keys},
            metrics={k: tuple(r.metrics.get(k) for r in runs) for k in metric_keys},
        )

    # --- Observations ---------------------------------------------------------------

    def get_observation(self, observation_id: str) -> Observation:
        return self._service.get_observation(observation_id)

    def list_observations(self, knowledge_graph: str) -> list[Observation]:
        """All Observations of the Knowledge Graph's Graph Source, oldest first."""
        return self._service.list_observations(knowledge_graph)


class ActiveRun:
    """A running Construction Run, as handed to the user's pipeline by `start_run`."""

    def __init__(
        self,
        service: TrackingService,
        graph_source: GraphSource,
        run: ConstructionRun,
        declared_ontology: Ontology,
    ) -> None:
        self._service = service
        self._graph_source = graph_source
        self.id = run.id
        self.knowledge_graph = run.knowledge_graph
        self.ontology_version = run.ontology_version
        self.declared_ontology = declared_ontology

    def log_param(self, key: str, value: object) -> None:
        self.log_params({key: value})

    def log_params(self, params: dict[str, object]) -> None:
        """Params are stored as strings; logging a key again replaces its value."""
        self._service.log_params(self.id, {k: str(v) for k, v in params.items()})

    def log_metric(self, key: str, value: float) -> None:
        self.log_metrics({key: value})

    def log_metrics(self, metrics: dict[str, float]) -> None:
        """Logging a key again replaces its value."""
        self._service.log_metrics(self.id, {k: float(v) for k, v in metrics.items()})

    def end(self) -> ConstructionRun:
        """End the run: observe the whole bound Graph Source scope and store the
        Observed Schema. If the Observation fails, the run is marked failed."""
        try:
            scope = self._service.get_graph_source(self.knowledge_graph)
            schema = self._graph_source.observe(scope)
        except BaseException:
            self._service.fail_run(self.id)
            raise
        return self._service.end_run(self.id, (scope, schema))

    def fail(self) -> ConstructionRun:
        """Abort the run; it is recorded as failed and nothing is observed."""
        return self._service.fail_run(self.id)

    def __enter__(self) -> ActiveRun:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._service.get_run(self.id).status != "running":
            return  # ended or failed explicitly inside the block
        if exc_type is None:
            self.end()
        else:
            self.fail()
