"""SqlStore reads the JSON columns of rows written by earlier releases.

The rows are inserted as literal text, exactly as those releases stored them, so a change
to the codec that stops reading them fails here."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, insert

from stetiq.conformance import Conformance, Mismatch, MismatchKind
from stetiq.drift import DriftFinding, DriftKind, DriftThresholds
from stetiq.evaluation.framework import Detail
from stetiq.gates import ConformanceGate, GateOutcome
from stetiq.graph_source import GraphSourceScope, ObservedNodeType, ObservedProperty, ObservedSchema
from stetiq.ontology import parse_dict
from stetiq.tracking import SqlStore, sql_store
from stetiq.tracking.entities import ConstructionRun, KnowledgeGraph, OntologyVersion

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
ISO = AT.isoformat()


@pytest.fixture
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'stetiq.db'}"
    store = SqlStore(url)
    store.add_knowledge_graph(KnowledgeGraph(name="support", created_at=AT))
    store.add_ontology_version(
        OntologyVersion(
            knowledge_graph="support",
            number=1,
            content_hash="h1",
            origin="registered",
            created_at=AT,
            ontology=parse_dict({"node_types": [{"label": "Customer"}]}),
        )
    )
    store.add_run(
        ConstructionRun(
            id="run-1",
            knowledge_graph="support",
            ontology_version=1,
            status="running",
            started_at=AT,
        )
    )
    engine = create_engine(url)
    yield store, engine
    engine.dispose()


def _insert(engine, table, **values):
    with engine.begin() as conn:
        conn.execute(insert(table).values(**values))


def test_reads_evaluation_details_as_earlier_releases_stored_them(db):
    store, engine = db
    _insert(
        engine,
        sql_store.evaluation_results,
        knowledge_graph="support",
        subject_kind="ontology_version",
        subject_id="1",
        evaluator="hierarchy",
        metrics_json='{"isolated": 1}',
        details_json=(
            '[{"item": "Customer", "message": "no relationships", "metric": "isolated"},'
            ' {"item": "q1", "message": "", "metric": null, "data": {"missing": ["Ticket"]}}]'
        ),
        created_at=ISO,
    )

    [result] = store.list_evaluation_results("support", "ontology_version")

    assert result.details == (
        Detail(item="Customer", message="no relationships", metric="isolated"),
        Detail(item="q1", data={"missing": ["Ticket"]}),
    )
    assert result.metrics == {"isolated": 1}
    assert result.parameters == {}


def test_reads_observations_and_drift_events_as_earlier_releases_stored_them(db):
    store, engine = db
    _insert(
        engine,
        sql_store.observations,
        id="obs-1",
        knowledge_graph="support",
        run_id=None,
        observed_at=ISO,
        scope_json='{"database": "kgs", "label": "KG_support", "namespace": null}',
        schema_json=(
            '{"node_types": [{"count": 3, "label": "Customer", "properties":'
            ' [{"count": 3, "fill_rate": 1.0, "name": "name", "types": ["STRING"]}]}],'
            ' "relationship_types": [], "patterns": []}'
        ),
    )
    _insert(
        engine,
        sql_store.drift_events,
        id="drift-1",
        knowledge_graph="support",
        observation_id="obs-1",
        previous_observation_id=None,
        contract_alias="production",
        ontology_version=1,
        detected_at=ISO,
        thresholds_json='{"max_count_drop": 0.5, "max_count_increase": null}',
        findings_json=(
            '[{"kind": "undeclared", "subject": "Invoice", "subject_kind": "node_type",'
            ' "detail": "", "previous_count": null, "observed_count": null}]'
        ),
    )

    [observation] = store.list_observations("support")
    [event] = store.list_drift_events("support")

    assert observation.scope == GraphSourceScope(database="kgs", label="KG_support")
    assert observation.schema == ObservedSchema(
        node_types=(
            ObservedNodeType("Customer", 3, (ObservedProperty("name", ("STRING",), 3, 1.0),)),
        ),
        relationship_types=(),
    )
    assert event.thresholds == DriftThresholds(max_count_drop=0.5)
    assert event.findings == (DriftFinding(DriftKind.UNDECLARED, "Invoice", "node_type"),)


def test_reads_run_conformance_and_gate_results_as_earlier_releases_stored_them(db):
    store, engine = db
    _insert(
        engine,
        sql_store.run_conformance,
        run_id="run-1",
        score=0.5,
        conformance_json=(
            '{"mismatches": [{"detail": "not observed", "kind": "absent",'
            ' "subject": "Ticket", "subject_kind": "node_type"}], "score": 0.5}'
        ),
    )
    _insert(
        engine,
        sql_store.gate_results,
        knowledge_graph="support",
        subject_kind="construction_run",
        subject_id="run-1",
        ontology_version=1,
        passed=0,
        outcomes_json=(
            '[{"gate": {"name": "conformant", "check": "conformance", "min_score": 0.8},'
            ' "passed": false, "reasons": ["0.5 < 0.8"]}]'
        ),
        evaluated_at=ISO,
    )

    run = store.get_run("run-1")
    [gate_result] = store.list_gate_results("support")

    assert run is not None
    assert run.conformance == Conformance(
        score=0.5,
        mismatches=(Mismatch("Ticket", "node_type", MismatchKind.ABSENT, "not observed"),),
    )
    assert gate_result.outcomes == (
        GateOutcome(ConformanceGate("conformant", 0.8), False, ("0.5 < 0.8",)),
    )
