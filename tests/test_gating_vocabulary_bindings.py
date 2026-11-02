"""The `ontology_diff` Gate weighs observed evidence for a Vocabulary binding: binding an
Attribute to a Vocabulary is breaking in the Ontology Diff, but the Gate accepts it when
the gated subject's Observed Schema shows every value of that Attribute inside the
Vocabulary. Through the SDK, against the in-memory fake Graph Source."""

from stetiq.graph_source import GraphSourceScope

KG = "plant"

# Version 1 (production): WorkOrder.kind is free text.
UNBOUND = """
node_types:
  - label: WorkOrder
    properties:
      - {name: id, type: STRING, required: true}
      - {name: kind, type: STRING}
      - {name: title, type: STRING}
"""

# Version 2: WorkOrder.kind bound to WorkOrderKind (the binding is breaking in the Diff).
BOUND = """
vocabularies:
  - label: WorkOrderKind
    values: [breakdown, preventive]
node_types:
  - label: WorkOrder
    properties:
      - {name: id, type: STRING, required: true}
      - {name: kind, type: STRING, vocabulary: WorkOrderKind}
      - {name: title, type: STRING}
"""

# Version 2, alternatively: the same binding, and WorkOrder.title removed (breaking too).
BOUND_WITHOUT_TITLE = """
vocabularies:
  - label: WorkOrderKind
    values: [breakdown, preventive]
node_types:
  - label: WorkOrder
    properties:
      - {name: id, type: STRING, required: true}
      - {name: kind, type: STRING, vocabulary: WorkOrderKind}
"""

NO_BREAKING = """
gates:
  - name: no-breaking-changes
    check: ontology_diff
    max_classification: additive
"""

ACCEPTED = (
    "binding WorkOrder.kind -> WorkOrderKind accepted: all observed values are in the Vocabulary"
)
BREAKING_BINDING = (
    "breaking change (v1 -> v2): changed WorkOrder.kind: bound to Vocabulary WorkOrderKind"
)


def make_plant(client, bound=BOUND):
    client.create_knowledge_graph(KG, ontology=UNBOUND)
    client.bind_graph_source(KG, GraphSourceScope(database="neo4j"))
    client.register_ontology(KG, bound)  # v2


def seed(graph_source, *kinds, titled=True):
    for n, kind in enumerate(kinds):
        props = {"id": f"WO-{n}"} | ({"title": "job"} if titled else {})
        if kind is not None:
            props["kind"] = kind
        graph_source.add_node(["WorkOrder"], props)


def run_on_v2(client):
    with client.start_run(KG, ontology_version=2) as run:
        pass
    return client.get_run(run.id)


def diff_gate(result):
    [outcome] = result.outcomes
    return outcome


def test_a_binding_every_observed_value_satisfies_passes_with_the_reason(client, graph_source):
    make_plant(client)
    seed(graph_source, "breakdown", "preventive", "breakdown")
    run = run_on_v2(client)

    outcome = diff_gate(client.evaluate_gates(KG, NO_BREAKING, run=run.id))

    assert outcome.passed
    assert outcome.reasons == (ACCEPTED,)


def test_a_value_outside_the_vocabulary_keeps_the_binding_breaking(client, graph_source):
    make_plant(client)
    # Strict, so the run yields no Candidate whose Vocabulary would take the value in.
    client.set_evolution_mode(KG, "strict")
    seed(graph_source, "breakdown", "corrective")
    run = run_on_v2(client)
    assert run.candidate_version is None

    outcome = diff_gate(client.evaluate_gates(KG, NO_BREAKING, run=run.id))

    assert not outcome.passed
    assert outcome.reasons == (BREAKING_BINDING,)


def test_a_truncated_value_list_is_no_evidence(client_factory, graph_source):
    client = client_factory(value_cap=1)
    make_plant(client)
    seed(graph_source, "breakdown", "breakdown", "preventive")  # both inside, list cut at 1
    run = run_on_v2(client)

    outcome = diff_gate(client.evaluate_gates(KG, NO_BREAKING, run=run.id))

    assert not outcome.passed
    assert outcome.reasons == (BREAKING_BINDING,)


def test_without_an_observation_the_binding_stays_breaking(client):
    make_plant(client)

    outcome = diff_gate(client.evaluate_gates(KG, NO_BREAKING, version=2))

    assert not outcome.passed
    assert outcome.reasons == (BREAKING_BINDING,)


def test_an_attribute_whose_values_were_not_observed_keeps_the_binding_breaking(
    client, graph_source
):
    make_plant(client)
    seed(graph_source, None, None)  # no WorkOrder holds a kind
    run = run_on_v2(client)

    outcome = diff_gate(client.evaluate_gates(KG, NO_BREAKING, run=run.id))

    assert not outcome.passed
    assert outcome.reasons == (BREAKING_BINDING,)


def test_an_accepted_binding_beside_another_breaking_change_still_fails(client, graph_source):
    make_plant(client, bound=BOUND_WITHOUT_TITLE)
    seed(graph_source, "breakdown", "preventive", titled=False)
    run = run_on_v2(client)

    outcome = diff_gate(client.evaluate_gates(KG, NO_BREAKING, run=run.id))

    assert not outcome.passed
    assert outcome.reasons == (
        "breaking change (v1 -> v2): removed WorkOrder.title: Attribute WorkOrder.title removed",
        ACCEPTED,
    )


USE_CASE = """
competency_questions:
  - id: breakdowns
    question: Which work orders were breakdowns?
    concepts: [WorkOrder.kind]
consumers:
  - id: dashboard
    name: Reliability dashboard
    tasks:
      - id: triage
        description: Triage breakdowns
        competency_questions: [breakdowns]
"""


def test_the_diff_and_consumer_impact_still_class_an_accepted_binding_as_breaking(
    client, graph_source
):
    make_plant(client)
    client.register_use_case(KG, USE_CASE)
    seed(graph_source, "breakdown", "preventive")
    run = run_on_v2(client)
    assert client.evaluate_gates(KG, NO_BREAKING, run=run.id).passed

    diff = client.diff_ontology_versions(KG, 1, 2)
    impact = client.consumer_impact(KG, 1, 2)

    assert diff.classification == "breaking"
    assert [(c.concept, c.classification) for c in diff.breaking] == [
        ("WorkOrder.kind", "breaking")
    ]
    assert [(c.id, c.level) for c in impact.consumers] == [("dashboard", "affected")]
