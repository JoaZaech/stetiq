"""The codec owns the JSON form of every tracking entity, for the wire and the Store alike.

Every dataclass in `stetiq.tracking.entities` is found automatically and must round-trip.
Its sample sets every defaulted field to a non-default value, so a field the codec drops
comes back as its default and the round trip fails."""

import dataclasses
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from stetiq.conformance import Conformance, Mismatch, MismatchKind
from stetiq.drift import DriftFinding, DriftKind, DriftThresholds
from stetiq.evaluation.framework import Detail, Evaluation
from stetiq.gates import ConformanceGate, GateOutcome
from stetiq.graph_source import GraphSourceScope, ObservedNodeType, ObservedSchema
from stetiq.ontology import parse_dict
from stetiq.tracking import codec, entities
from stetiq.tracking.entities import (
    Alias,
    ConstructionRun,
    DriftEvent,
    EvaluationResult,
    GatePreview,
    GatePreviewSource,
    GateResult,
    KnowledgeGraph,
    KnowledgeGraphSummary,
    Observation,
    ObservationOutcome,
    OntologyVersion,
    Promotion,
    RunComparison,
    UseCaseVersion,
)
from stetiq.use_case import parse_use_case_dict

# Composed by `Client` from other entities; never sent over the wire or stored.
NOT_ENCODED = {RunComparison}

# Values the codec writes itself (not through another module's `to_dict`), checked like entities.
CODEC_VALUES = [Detail, Evaluation]

ENTITY_TYPES = [
    cls
    for cls in vars(entities).values()
    if isinstance(cls, type)
    and dataclasses.is_dataclass(cls)
    and cls.__module__ == entities.__name__
    and cls not in NOT_ENCODED
]

AT = datetime(2026, 10, 31, 12, 30, tzinfo=UTC)
LATER = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)

ONTOLOGY = parse_dict(
    {
        "node_types": [{"label": "Customer"}, {"label": "Ticket"}],
        "relationship_types": [{"label": "OPENED"}],
        "patterns": [["Customer", "OPENED", "Ticket"]],
    }
)
USE_CASE = parse_use_case_dict(
    {
        "competency_questions": [{"id": "q1", "question": "Which customers opened tickets?"}],
        "consumers": [
            {
                "id": "triage-bot",
                "name": "Triage bot",
                "kind": "agent",
                "contact": "Ada",
                "description": "Routes tickets",
                "tasks": [
                    {"id": "route", "description": "Route a ticket", "competency_questions": ["q1"]}
                ],
            }
        ],
    }
)
SCOPE = GraphSourceScope(database="kgs", label="KG_support", namespace="support")
SCHEMA = ObservedSchema(node_types=(ObservedNodeType("Customer", 3, ()),), relationship_types=())
DETAIL = Detail(item="Customer", message="isolated", metric="isolated", data={"missing": ["x"]})
KNOWLEDGE_GRAPH = KnowledgeGraph(name="support", created_at=AT, description="Support tickets")
OBSERVATION = Observation(
    id="obs-1",
    knowledge_graph="support",
    scope=SCOPE,
    observed_at=AT,
    schema=SCHEMA,
    run_id="run-1",
)
DRIFT_EVENT = DriftEvent(
    id="drift-1",
    knowledge_graph="support",
    observation_id="obs-2",
    previous_observation_id="obs-1",
    contract_alias="production",
    ontology_version=2,
    detected_at=LATER,
    findings=(
        DriftFinding(DriftKind.COUNT_DROP, "Customer", "node_type", "fell", 10, 3),
        DriftFinding(DriftKind.UNDECLARED, "Invoice", "node_type"),
    ),
    thresholds=DriftThresholds(max_count_drop=0.5, max_count_increase=2.0),
)

GATE_PREVIEW_SOURCE = GatePreviewSource(
    subject_kind="ontology_version", subject_id="2", evaluated_at=LATER
)

SAMPLES: dict[type, Any] = {
    KnowledgeGraph: KNOWLEDGE_GRAPH,
    KnowledgeGraphSummary: KnowledgeGraphSummary(
        knowledge_graph=KNOWLEDGE_GRAPH,
        contract_version=1,
        latest_version=3,
        last_run_status="finished",
        last_modified_at=LATER,
    ),
    OntologyVersion: OntologyVersion(
        knowledge_graph="support",
        number=2,
        content_hash="abc123",
        origin="run",
        created_at=AT,
        ontology=ONTOLOGY,
    ),
    ConstructionRun: ConstructionRun(
        id="run-1",
        knowledge_graph="support",
        ontology_version=1,
        status="finished",
        started_at=AT,
        ended_at=LATER,
        params={"model": "gpt"},
        metrics={"nodes": 3.0},
        observation_id="obs-1",
        conformance=Conformance(
            score=0.5,
            mismatches=(Mismatch("Ticket", "node_type", MismatchKind.ABSENT, "not observed"),),
        ),
        candidate_version=2,
    ),
    Observation: OBSERVATION,
    Alias: Alias(knowledge_graph="support", name="staging", version=2, updated_at=AT),
    Promotion: Promotion(
        knowledge_graph="support",
        alias="production",
        from_version=1,
        to_version=2,
        actor="ada",
        promoted_at=AT,
        gate_result="passed",
    ),
    EvaluationResult: EvaluationResult(
        knowledge_graph="support",
        subject_kind="ontology_version",
        subject_id="2",
        evaluator="structural_answerability",
        metrics={"answerable": 0.5},
        details=(DETAIL,),
        created_at=AT,
        parameters={"reference_version": 1},
        use_case_version=3,
    ),
    UseCaseVersion: UseCaseVersion(
        knowledge_graph="support", number=1, content_hash="def456", created_at=AT, use_case=USE_CASE
    ),
    DriftEvent: DRIFT_EVENT,
    ObservationOutcome: ObservationOutcome(observation=OBSERVATION, drift=DRIFT_EVENT),
    GateResult: GateResult(
        knowledge_graph="support",
        subject_kind="construction_run",
        subject_id="run-1",
        ontology_version=2,
        outcomes=(GateOutcome(ConformanceGate("conformant", 0.8), False, ("0.5 < 0.8",)),),
        evaluated_at=AT,
    ),
    GatePreviewSource: GATE_PREVIEW_SOURCE,
    GatePreview: GatePreview(
        knowledge_graph="support",
        subject_kind="construction_run",
        subject_id="run-2",
        ontology_version=3,
        outcomes=(GateOutcome(ConformanceGate("conformant", 0.8), True, ("0.9 >= 0.8",)),),
        source=GATE_PREVIEW_SOURCE,
    ),
    Detail: DETAIL,
    Evaluation: Evaluation(metrics={"score": 1.0}, details=(DETAIL,)),
}


def _assert_no_defaults(value: Any, path: str) -> None:
    """Every defaulted field of `value` (and of the entities inside it) holds a non-default."""
    if isinstance(value, tuple):
        for i, item in enumerate(value):
            _assert_no_defaults(item, f"{path}[{i}]")
        return
    if type(value) not in ENTITY_TYPES + CODEC_VALUES:
        return
    for f in dataclasses.fields(value):
        held = getattr(value, f.name)
        if f.default is not dataclasses.MISSING:
            assert held != f.default, f"{path}.{f.name} holds its default; give it another value"
        if f.default_factory is not dataclasses.MISSING:
            assert held != f.default_factory(), (
                f"{path}.{f.name} holds its default; give it another value"
            )
        _assert_no_defaults(held, f"{path}.{f.name}")


@pytest.mark.parametrize("cls", ENTITY_TYPES + CODEC_VALUES, ids=lambda cls: cls.__name__)
def test_every_entity_round_trips_through_the_codec(cls):
    assert cls in SAMPLES, f"add a sample {cls.__name__} to SAMPLES"
    sample = SAMPLES[cls]
    _assert_no_defaults(sample, cls.__name__)

    data = json.loads(json.dumps(codec.encode(sample)))

    assert codec.decode(cls, data) == sample


def test_the_entity_list_is_found_automatically():
    assert {KnowledgeGraph, OntologyVersion, GateResult, ObservationOutcome} <= set(ENTITY_TYPES)


def test_a_use_case_version_payload_from_before_consumers_still_parses():
    data = {
        "knowledge_graph": "support",
        "number": 1,
        "content_hash": "def456",
        "created_at": AT.isoformat(),
        "use_case": {"competency_questions": [{"id": "q1", "question": "Which customers?"}]},
    }

    version = codec.use_case_version_from_json(data)

    assert version.use_case.consumers == ()
    assert [q.id for q in version.use_case.competency_questions] == ["q1"]
