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


def test_registering_a_use_case_version_judges_the_latest_ontology_version_against_it(client, kg):
    client.register_ontology(kg.name, WITHOUT_OPENED)

    client.register_use_case(kg.name, USE_CASE)

    latest = answerability(client.get_evaluation_results(kg.name, 2))
    assert latest.use_case_version == 1
    assert latest.metrics["unanswerable_questions"] == 1
    # Only the latest Ontology Version is judged.
    assert "structural_answerability" not in {
        r.evaluator for r in client.get_evaluation_results(kg.name, 1)
    }


def test_registering_an_unchanged_use_case_judges_nothing_again(client, kg):
    client.register_use_case(kg.name, USE_CASE)
    judged = answerability(client.get_evaluation_results(kg.name, 1))

    client.register_use_case(kg.name, USE_CASE)

    assert answerability(client.get_evaluation_results(kg.name, 1)) == judged


def test_a_new_use_case_version_does_not_re_run_the_other_built_ins(client, kg):
    before = {r.evaluator: r for r in client.get_evaluation_results(kg.name, 1)}

    client.register_use_case(kg.name, USE_CASE)

    after = {r.evaluator: r for r in client.get_evaluation_results(kg.name, 1)}
    assert set(after) == set(before) | {"structural_answerability"}
    assert all(after[name] == result for name, result in before.items())


def test_a_new_ontology_version_reports_unanswerable_questions_with_the_missing_concepts(
    client, kg
):
    client.register_use_case(kg.name, USE_CASE)

    version = client.register_ontology(kg.name, WITHOUT_OPENED)

    result = answerability(client.get_evaluation_results(kg.name, version.number))
    assert result.use_case_version == 1
    assert (result.metrics["answerable_questions"], result.metrics["unanswerable_questions"]) == (
        1,
        1,
    )
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


@pytest.mark.parametrize(
    "questions, message",
    [
        (
            (CompetencyQuestion("a", "x"), CompetencyQuestion("a", "y")),
            "a: duplicate competency question id",
        ),
        (
            (CompetencyQuestion("a", "x", expected_answer={1, 2}),),
            "a.expected_answer: must be a JSON value (strings, numbers, lists, mappings)",
        ),
        (
            (CompetencyQuestion(None, "x"), CompetencyQuestion("b", "y")),  # type: ignore[arg-type]
            "competency question.id: needs a non-empty string id",
        ),
    ],
)
def test_a_malformed_use_case_model_is_rejected_with_the_same_message_in_every_mode(
    client, kg, questions, message
):
    with pytest.raises(stetiq.UseCaseValidationError) as raised:
        client.register_use_case(kg.name, stetiq.UseCase(competency_questions=questions))

    assert str(raised.value) == message


def test_adding_a_question_with_an_existing_id_is_rejected(client, kg):
    client.register_use_case(kg.name, USE_CASE)

    with pytest.raises(stetiq.UseCaseValidationError, match="customer-names"):
        client.add_competency_question(
            kg.name, CompetencyQuestion(id="customer-names", question="Again?")
        )


def test_without_a_number_the_latest_use_case_version_is_returned(client, kg):
    with pytest.raises(stetiq.NoUseCaseError) as raised:
        client.get_use_case_version(kg.name)
    assert str(raised.value) == "Knowledge Graph 'customer-support-kg' has no Use Case"
    assert isinstance(raised.value, stetiq.NotFoundError)

    client.register_use_case(kg.name, USE_CASE)
    client.add_competency_question(kg.name, CompetencyQuestion(id="extra", question="More?"))

    assert client.get_use_case_version(kg.name).number == 2


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
    """A deterministic stand-in for the LLM behind the model interface."""

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
        from stetiq.auth import TokenRegistry

        _, token = TokenRegistry(url).issue("tester", {"*": "edit"})
        with TestClient(create_app(url, question_mapper=mapper)) as http:
            base = str(http.base_url)
            service = RemoteTrackingService(base, http=http, token=token)
            yield stetiq.Client(base, service=service), mapper


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

    # Registering the Use Case judged v1 against it.
    questions = per_question(answerability(client.get_evaluation_results("kg", 1)))

    assert mapper.asked == ["happy", "names"]
    assert questions["happy"] == {
        "status": "unanswerable",
        "source": "model",
        "required": ["Customer.satisfaction"],
        "missing": ["Customer.satisfaction"],
    }
    assert (questions["names"]["status"], questions["names"]["source"]) == ("answerable", "model")
    assert questions["explicit"]["source"] == "concepts"


# --- Consumers and Tasks -----------------------------------------------------------

WITH_CONSUMERS = (
    USE_CASE
    + """
consumers:
  - id: triage-bot
    name: Triage bot
    kind: agent
    contact: Ada Lovelace
    description: Routes new tickets to the right team.
    tasks:
      - id: route-ticket
        description: Route a new ticket by the customer's history
        competency_questions: [tickets-per-customer, customer-names]
  - id: support-dashboard
    name: Support dashboard
    tasks:
      - id: show-workload
        description: Show each customer's open tickets
        competency_questions: [tickets-per-customer]
"""
)


def test_a_use_case_declares_consumers_whose_tasks_need_competency_questions(client, kg):
    version = client.register_use_case(kg.name, WITH_CONSUMERS)

    consumers = {
        c.id: c for c in client.get_use_case_version(kg.name, version.number).use_case.consumers
    }
    bot = consumers["triage-bot"]
    assert (bot.name, bot.kind, bot.contact, bot.description) == (
        "Triage bot",
        "agent",
        "Ada Lovelace",
        "Routes new tickets to the right team.",
    )
    assert [(t.id, t.description, t.competency_questions) for t in bot.tasks] == [
        (
            "route-ticket",
            "Route a new ticket by the customer's history",
            ("customer-names", "tickets-per-customer"),
        )
    ]
    dashboard = consumers["support-dashboard"]
    assert (dashboard.kind, dashboard.contact, dashboard.description) == (None, None, None)
    assert dashboard.tasks[0].competency_questions == ("tickets-per-customer",)


def test_a_use_case_with_consumers_can_be_given_as_a_model(client, kg):
    use_case = stetiq.UseCase(
        competency_questions=(CompetencyQuestion("q", "Which customers are there?"),),
        consumers=(
            stetiq.Consumer(
                id="crm",
                name="CRM sync",
                kind="application",
                tasks=(stetiq.Task("sync", "Sync customers", competency_questions=("q",)),),
            ),
        ),
    )

    version = client.register_use_case(kg.name, use_case)

    assert version.use_case.consumers == use_case.consumers


def test_a_use_case_with_consumers_can_be_given_as_a_dict(client, kg):
    version = client.register_use_case(
        kg.name,
        {
            "competency_questions": [{"id": "q", "question": "Which customers are there?"}],
            "consumers": [
                {
                    "id": "crm",
                    "name": "CRM sync",
                    "tasks": [
                        {
                            "id": "sync",
                            "description": "Sync customers",
                            "competency_questions": ["q"],
                        }
                    ],
                }
            ],
        },
    )

    assert version.use_case.consumers == (
        stetiq.Consumer(
            id="crm",
            name="CRM sync",
            tasks=(stetiq.Task("sync", "Sync customers", competency_questions=("q",)),),
        ),
    )


def test_a_use_case_without_consumers_hashes_as_it_did_before_consumers_existed(client, kg):
    version = client.register_use_case(kg.name, USE_CASE)

    # Computed by the code before Consumers were added: older Use Case Versions still dedupe.
    assert (
        version.content_hash == "40b7935ea9ce53e9a32a747efa2defe48c5189a499cf54a47825468d266544d4"
    )
    assert version.use_case.consumers == ()


@pytest.mark.parametrize(
    "change",
    [
        lambda y: y.replace("  - id: support-dashboard", "  - id: dashboard"),
        lambda y: y.replace("kind: agent", "kind: bot"),
        lambda y: y.replace("competency_questions: [tickets-per-customer]\n", ""),
        lambda y: y.replace(
            "      - id: show-workload\n",
            "      - id: list-customers\n"
            "        description: List customers\n"
            "      - id: show-workload\n",
        ),
        lambda y: y.split("  - id: support-dashboard")[0],
    ],
    ids=["consumer-id", "consumer-kind", "task-questions", "task-added", "consumer-removed"],
)
def test_changing_consumers_or_tasks_yields_a_new_use_case_version(client, kg, change):
    first = client.register_use_case(kg.name, WITH_CONSUMERS)

    changed = client.register_use_case(kg.name, change(WITH_CONSUMERS))

    assert (first.number, changed.number) == (1, 2)
    assert changed.content_hash != first.content_hash


def test_consumers_and_tasks_in_another_order_are_the_same_use_case_version(client, kg):
    first = client.register_use_case(kg.name, WITH_CONSUMERS)
    reordered = WITH_CONSUMERS.replace(
        "[tickets-per-customer, customer-names]", "[customer-names, tickets-per-customer]"
    )
    swapped = stetiq.UseCase(
        competency_questions=first.use_case.competency_questions,
        description=first.use_case.description,
        consumers=tuple(reversed(first.use_case.consumers)),
    )

    assert client.register_use_case(kg.name, reordered).number == 1
    assert client.register_use_case(kg.name, swapped).number == 1
    assert len(client.list_use_case_versions(kg.name)) == 1


def test_adding_a_competency_question_keeps_the_consumers_and_tasks(client, kg):
    first = client.register_use_case(kg.name, WITH_CONSUMERS)

    version = client.add_competency_question(
        kg.name, CompetencyQuestion(id="ticket-count", question="How many tickets are open?")
    )

    assert version.number == 2
    assert version.use_case.consumers == first.use_case.consumers


QUESTIONS = "competency_questions: [{id: q, question: Who are our customers}]\n"


@pytest.mark.parametrize(
    "consumers, message",
    [
        (
            "[{id: crm, name: CRM, tasks: [{id: sync, description: Sync, competency_questions: [nope]}]}]",
            "sync.competency_questions: unknown competency question 'nope'",
        ),
        ("[{id: crm, name: CRM}, {id: crm, name: CRM again}]", "crm: duplicate consumer id"),
        (
            "[{id: crm, name: CRM, tasks: [{id: sync, description: Sync}]},"
            " {id: bi, name: BI, tasks: [{id: sync, description: Report}]}]",
            "sync: duplicate task id",
        ),
        ("[{name: CRM}]", "consumer.id: needs a non-empty string id"),
        (
            "[{id: crm, name: CRM, tasks: [{description: Sync}]}]",
            "crm task.id: needs a non-empty string id",
        ),
        ("[{id: crm}]", "crm.name: needs a name"),
        ("[{id: crm, name: CRM, tasks: [{id: sync}]}]", "sync.description: needs a description"),
        ("[{id: crm, name: CRM, owner: Ada}]", "consumers[0]: unknown keys ['owner']"),
        ("[{id: crm, name: CRM, tasks: sync}]", "consumers[0].tasks: must be a list"),
    ],
)
def test_malformed_consumers_are_rejected_naming_the_element_in_every_mode(
    client, kg, consumers, message
):
    with pytest.raises(stetiq.UseCaseValidationError) as raised:
        client.register_use_case(kg.name, QUESTIONS + "consumers: " + consumers)

    assert str(raised.value) == message
    assert client.list_use_case_versions(kg.name) == []


@pytest.mark.parametrize(
    "consumers, message",
    [
        (
            (stetiq.Consumer("crm", "CRM", tasks=(stetiq.Task("sync", "Sync", ("nope",)),)),),
            "sync.competency_questions: unknown competency question 'nope'",
        ),
        (
            (stetiq.Consumer("crm", "CRM"), stetiq.Consumer("crm", "CRM again")),
            "crm: duplicate consumer id",
        ),
        (
            (stetiq.Consumer(None, "CRM"),),  # type: ignore[arg-type]
            "consumer.id: needs a non-empty string id",
        ),
        (
            (stetiq.Consumer("crm", "CRM", tasks=(stetiq.Task("", "Sync"),)),),
            "crm task.id: needs a non-empty string id",
        ),
    ],
)
def test_a_malformed_consumer_model_is_rejected_with_the_same_message_in_every_mode(
    client, kg, consumers, message
):
    use_case = stetiq.UseCase(
        competency_questions=(CompetencyQuestion("q", "Which customers are there?"),),
        consumers=consumers,
    )

    with pytest.raises(stetiq.UseCaseValidationError) as raised:
        client.register_use_case(kg.name, use_case)

    assert str(raised.value) == message
