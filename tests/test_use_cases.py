"""Use Cases (versioned sets of Competency Questions) and structural answerability."""

import pytest

import stetiq
from stetiq import CompetencyQuestion

USE_CASE = """
description: Support agents triage tickets
competency_questions:
  - id: tickets-per-customer
    question: Which tickets did a given customer open?
    query: >
      MATCH (c:Customer {name: $name})-[:OPENED]->(t:Ticket)
      RETURN t.opened_at
  - id: customer-names
    question: What are our customers called?
    concepts: [Customer.name]
"""


@pytest.fixture
def kg(client, support_ontology):
    return client.create_knowledge_graph("customer-support-kg", ontology=support_ontology)


def test_a_use_case_is_registered_as_version_one_of_the_knowledge_graphs_use_case(client, kg):
    version = client.register_use_case(kg.name, USE_CASE)

    assert (version.knowledge_graph, version.number) == (kg.name, 1)
    assert version.use_case.description == "Support agents triage tickets"
    questions = {q.id: q for q in version.use_case.competency_questions}
    assert questions["tickets-per-customer"].question == "Which tickets did a given customer open?"
    assert questions["tickets-per-customer"].query.startswith("MATCH (c:Customer")
    assert questions["customer-names"].concepts == ("Customer.name",)
    assert questions["customer-names"].query is None


def test_adding_a_question_creates_a_new_use_case_version_not_a_new_ontology_version(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    version = client.add_competency_question(
        kg.name,
        CompetencyQuestion(
            id="ticket-count",
            question="How many tickets are open?",
            query="MATCH (t:Ticket) RETURN count(t)",
            expected_answer=[{"count(t)": 3}],
        ),
    )

    assert version.number == 2
    assert [q.id for q in version.use_case.competency_questions] == [
        "customer-names",
        "ticket-count",
        "tickets-per-customer",
    ]
    assert [v.number for v in client.list_use_case_versions(kg.name)] == [1, 2]
    assert [v.number for v in client.list_ontology_versions(kg.name)] == [1]
    fetched = client.get_use_case_version(kg.name, 2).use_case.competency_question("ticket-count")
    assert fetched.expected_answer == [{"count(t)": 3}]


def answerability(results):
    return {r.evaluator: r for r in results}["structural_answerability"]


def per_question(result):
    return {d.item: d.data for d in result.details}


def test_an_existing_ontology_version_is_re_evaluated_against_a_new_use_case_version(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    result = answerability(client.evaluate(kg.name, 1))

    assert result.use_case_version == 1
    assert result.metrics == {
        "questions": 2,
        "answerable_questions": 2,
        "unanswerable_questions": 0,
        "unmapped_questions": 0,
        "answerable_ratio": 1.0,
    }
    assert per_question(result)["tickets-per-customer"] == {
        "status": "answerable",
        "source": "query",
        "required": [
            "Customer",
            "Customer.name",
            "OPENED",
            "Ticket",
            "(Customer)-[OPENED]->(Ticket)",
            "Ticket.opened_at",
        ],
        "missing": [],
    }
    assert answerability(client.get_evaluation_results(kg.name, 1)).use_case_version == 1


# Ticket.opened_at and the OPENED relationship are gone; Customer.name stays.
WITHOUT_OPENED = """
node_types:
  - label: Customer
    properties: [{name: name, type: STRING, required: true}]
  - Ticket
relationship_types: [FILED]
patterns:
  - [Customer, FILED, Ticket]
"""


def test_a_new_ontology_version_reports_unanswerable_questions_with_the_missing_concepts(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    version = client.register_ontology(kg.name, WITHOUT_OPENED)

    result = answerability(client.get_evaluation_results(kg.name, version.number))
    assert result.use_case_version == 1
    assert (result.metrics["answerable_questions"], result.metrics["unanswerable_questions"]) == (1, 1)
    assert result.metrics["answerable_ratio"] == 0.5
    questions = per_question(result)
    assert questions["customer-names"]["status"] == "answerable"
    assert questions["tickets-per-customer"]["status"] == "unanswerable"
    assert questions["tickets-per-customer"]["missing"] == ["OPENED", "Ticket.opened_at"]
    detail = next(d for d in result.details if d.item == "tickets-per-customer")
    assert detail.metric == "unanswerable_questions"
    assert detail.message == "missing OPENED, Ticket.opened_at"


HIERARCHY = """
node_types:
  - label: Party
    properties: [{name: name, type: STRING}]
  - {label: Customer, parent: Party}
  - Ticket
  - Agent
relationship_types: [OPENED]
patterns:
  - [Party, OPENED, Ticket]
"""


def test_explicit_concept_mappings_match_through_the_hierarchy_and_report_missing_paths(client):
    client.create_knowledge_graph("kg", ontology=HIERARCHY)
    client.register_use_case(
        "kg",
        [
            CompetencyQuestion(
                id="inherited",
                question="What are the names of customers who opened tickets?",
                concepts=("(Customer)-[OPENED]->(Ticket)", "Customer.name"),
            ),
            CompetencyQuestion(
                id="no-path",
                question="Which tickets did an agent open?",
                concepts=("(Agent)-[OPENED]->(Ticket)",),
            ),
            CompetencyQuestion(
                id="missing-type",
                question="Which supervisors handle tickets?",
                concepts=("(Supervisor)-[HANDLES]->(Ticket)",),
            ),
        ],
    )

    questions = per_question(answerability(client.evaluate("kg", 1)))

    assert questions["inherited"]["status"] == "answerable"
    assert questions["inherited"]["source"] == "concepts"
    assert questions["no-path"]["missing"] == ["(Agent)-[OPENED]->(Ticket)"]
    # The missing pieces are reported rather than the path they are part of.
    assert questions["missing-type"]["missing"] == ["Supervisor", "HANDLES"]


def test_a_question_without_query_or_concept_mapping_is_unmapped(client, kg):
    client.register_use_case(
        kg.name, [CompetencyQuestion(id="vague", question="Are our customers happy?")]
    )

    result = answerability(client.evaluate(kg.name, 1))

    assert result.metrics["unmapped_questions"] == 1
    assert result.metrics["answerable_questions"] == 0
    assert per_question(result)["vague"] == {
        "status": "unmapped",
        "source": None,
        "required": [],
        "missing": [],
    }


def test_evaluation_can_be_pinned_to_an_earlier_use_case_version(client, kg):
    client.register_use_case(kg.name, USE_CASE)
    client.add_competency_question(
        kg.name, {"id": "agents", "question": "Who handles tickets?", "concepts": ["Agent"]}
    )

    pinned = answerability(client.evaluate(kg.name, 1, use_case_version=1))
    latest = answerability(client.evaluate(kg.name, 1))

    assert (pinned.use_case_version, pinned.metrics["questions"]) == (1, 2)
    assert (latest.use_case_version, latest.metrics["questions"]) == (2, 3)
    assert per_question(latest)["agents"]["missing"] == ["Agent"]
    with pytest.raises(stetiq.NotFoundError):
        client.evaluate(kg.name, 1, use_case_version=9)


def test_without_a_use_case_there_is_no_answerability_result(client, kg):
    results = client.evaluate(kg.name, 1)

    assert "structural_answerability" not in {r.evaluator for r in results}
    assert all(r.use_case_version is None for r in results)


def test_identical_use_case_content_returns_the_existing_version(client, kg):
    first = client.register_use_case(kg.name, USE_CASE)

    again = client.register_use_case(kg.name, USE_CASE)

    assert (again.number, again.content_hash) == (1, first.content_hash)
    assert len(client.list_use_case_versions(kg.name)) == 1


@pytest.mark.parametrize(
    "use_case, message",
    [
        ("competency_questions: []", "at least one question"),
        ("competency_questions: [{id: a}]", r"a\.question"),
        (
            "competency_questions: [{id: a, question: x}, {id: a, question: y}]",
            "duplicate",
        ),
        ("competency_questions: [{id: a, question: x, concepts: ['(A)-[R]']}]", r"a\.concepts"),
        ("competency_questions: [{id: a, question: x, answer: 3}]", "unknown keys"),
    ],
)
def test_malformed_use_cases_are_rejected_naming_the_element(client, kg, use_case, message):
    with pytest.raises(stetiq.UseCaseValidationError, match=message):
        client.register_use_case(kg.name, use_case)

    assert client.list_use_case_versions(kg.name) == []


def test_adding_a_question_with_an_existing_id_is_rejected(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    with pytest.raises(stetiq.UseCaseValidationError, match="customer-names"):
        client.add_competency_question(
            kg.name, CompetencyQuestion(id="customer-names", question="Again?")
        )


def test_a_use_case_needs_an_existing_knowledge_graph(client):
    with pytest.raises(stetiq.NotFoundError):
        client.register_use_case("nope", USE_CASE)


def test_a_custom_evaluator_cannot_take_the_answerability_name(client):
    class Impostor(stetiq.OntologyVersionEvaluator):
        name = "structural_answerability"

        def evaluate(self, version):
            return stetiq.Evaluation(metrics={})

    with pytest.raises(stetiq.EvaluatorError, match="structural_answerability"):
        client.register_evaluator(Impostor())


@pytest.mark.parametrize(
    "query, required, missing",
    [
        (
            "MATCH (t:Ticket)<-[:OPENED]-(c:Customer) WHERE c.name = 'x (y)' RETURN t",
            ["Ticket", "OPENED", "Customer", "(Customer)-[OPENED]->(Ticket)", "Customer.name"],
            [],
        ),
        (
            "MATCH (t:Ticket)-[:OPENED]-(c) RETURN count(t)",
            ["Ticket", "OPENED", "(Ticket)-[OPENED]-()"],
            [],
        ),
        (
            "MATCH (t:Ticket)-[:OPENED]->(c:Customer) RETURN c",  # wrong direction
            ["Ticket", "OPENED", "Customer", "(Ticket)-[OPENED]->(Customer)"],
            ["(Ticket)-[OPENED]->(Customer)"],
        ),
        (
            "MATCH (c:Customer)-[o:OPENED|FILED {via: 'web'}]->(t) // comment (x:Agent)\n"
            "RETURN o.via, t.priority",
            ["Customer", "OPENED|FILED", "OPENED|FILED.via", "(Customer)-[OPENED|FILED]->()"],
            ["OPENED|FILED.via"],
        ),
        (
            "MATCH (c:Customer)-[:OPENED*1..3]->(:`Ticket`) RETURN c",
            ["Customer", "OPENED", "Ticket"],
            [],
        ),
    ],
)
def test_the_concepts_and_paths_a_query_uses_are_read_from_its_cypher(
    client, kg, query, required, missing
):
    client.register_use_case(kg.name, [CompetencyQuestion(id="q", question="?", query=query)])

    q = per_question(answerability(client.evaluate(kg.name, 1)))["q"]

    assert (q["source"], q["required"], q["missing"]) == ("query", required, missing)


class StubMapper:
    """A deterministic stand-in for the LLM behind the model interface (ticket #12)."""

    def __init__(self):
        self.asked = []

    def map_question(self, question, ontology):
        self.asked.append(question.id)
        return {"happy": ["Customer.satisfaction"], "names": ["Customer.name"]}.get(question.id, [])


@pytest.fixture(params=["local", "remote"])
def mapped_client(request, tmp_path):
    from fastapi.testclient import TestClient

    from stetiq.server import create_app
    from stetiq.tracking import LocalTrackingService, RemoteTrackingService, SqlStore

    mapper = StubMapper()
    url = f"sqlite:///{tmp_path / 'stetiq.db'}"
    if request.param == "local":
        service = LocalTrackingService(SqlStore(url), question_mapper=mapper)
        yield stetiq.Client(url, service=service), mapper
    else:
        with TestClient(create_app(url, question_mapper=mapper)) as http:
            base = str(http.base_url)
            yield stetiq.Client(base, service=RemoteTrackingService(base, http=http)), mapper


def test_questions_without_a_query_or_mapping_are_mapped_through_the_model_interface(
    mapped_client, support_ontology
):
    client, mapper = mapped_client
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case(
        "kg",
        [
            CompetencyQuestion(id="happy", question="Are our customers happy?"),
            CompetencyQuestion(id="names", question="What are customers called?"),
            CompetencyQuestion(id="explicit", question="Tickets?", concepts=("Ticket",)),
        ],
    )

    questions = per_question(answerability(client.evaluate("kg", 1)))

    assert mapper.asked == ["happy", "names"]
    assert questions["happy"] == {
        "status": "unanswerable",
        "source": "model",
        "required": ["Customer.satisfaction"],
        "missing": ["Customer.satisfaction"],
    }
    assert (questions["names"]["status"], questions["names"]["source"]) == ("answerable", "model")
    assert questions["explicit"]["source"] == "concepts"
