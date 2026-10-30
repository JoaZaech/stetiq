"""LLM-assisted Competency Question mapping.

The LLM sits behind the `CompetencyQuestionMapper` model interface. These tests
drive it through the public SDK with a deterministic fake Anthropic client (the
system boundary), so no live LLM is ever called.
"""

import json
from types import SimpleNamespace

import pytest

import stetiq
from stetiq import CompetencyQuestion, LlmQuestionMapper


REFUSAL = SimpleNamespace(stop_reason="refusal", content=[])


class FakeAnthropic:
    """Stands in for `anthropic.Anthropic()`: answers `messages.create` from a script."""

    def __init__(self, answers):
        self.answers = answers  # question text -> concepts list, or an Exception
        self.requests = []
        self.messages = self
        self.beta = SimpleNamespace(messages=self)

    def create(self, **request):
        self.requests.append(request)
        prompt = request["messages"][-1]["content"]
        for question, answer in self.answers.items():
            if question in prompt:
                if isinstance(answer, Exception):
                    raise answer
                if isinstance(answer, SimpleNamespace):
                    return answer
                text = json.dumps({"concepts": answer})
                return SimpleNamespace(
                    stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)]
                )
        raise AssertionError(f"unexpected prompt: {prompt}")


def _client_with_mapper(mode, tmp_path, mapper):
    """A Client in `mode` whose tracking service maps questions with `mapper`."""
    from fastapi.testclient import TestClient

    from stetiq.server import create_app
    from stetiq.tracking import LocalTrackingService, RemoteTrackingService, SqlStore

    url = f"sqlite:///{tmp_path / 'stetiq.db'}"
    if mode == "local":
        yield stetiq.Client(url, service=LocalTrackingService(SqlStore(url), question_mapper=mapper))
        return
    from stetiq.auth import TokenRegistry

    _, token = TokenRegistry(url).issue("tester", {"*": "edit"})
    with TestClient(create_app(url, question_mapper=mapper)) as http:
        base = str(http.base_url)
        yield stetiq.Client(base, service=RemoteTrackingService(base, http=http, token=token))


@pytest.fixture(params=["local", "remote"])
def llm(request, tmp_path):
    """(client, fake Anthropic) with an `LlmQuestionMapper` injected into the service."""
    fake = FakeAnthropic(
        {
            "Are our customers happy?": ["Customer.satisfaction"],
            "What are customers called?": ["Customer.name"],
            "Who raised which ticket?": ["(Customer)-[RAISED]->(Ticket)", "not a (reference"],
            "Which tickets are urgent?": RuntimeError("model overloaded"),
            "Write me a poem": REFUSAL,
        }
    )
    mapper = LlmQuestionMapper(client=fake, model="claude-test-model")
    for client in _client_with_mapper(request.param, tmp_path, mapper):
        yield client, fake


def answerability(results):
    return {r.evaluator: r for r in results}["structural_answerability"]


def per_question(result):
    return {d.item: d.data for d in result.details}


def test_questions_without_a_query_are_mapped_by_the_llm_and_judged(llm, support_ontology):
    client, _ = llm
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case(
        "kg",
        [
            CompetencyQuestion(id="happy", question="Are our customers happy?"),
            CompetencyQuestion(id="names", question="What are customers called?"),
        ],
    )

    questions = per_question(answerability(client.evaluate("kg", 1)))

    assert questions["happy"]["status"] == "unanswerable"
    assert questions["happy"]["source"] == "model"
    assert questions["happy"]["required"] == ["Customer.satisfaction"]
    assert questions["happy"]["missing"] == ["Customer.satisfaction"]
    assert (questions["names"]["status"], questions["names"]["required"]) == (
        "answerable",
        ["Customer.name"],
    )


def test_the_llm_is_asked_with_the_question_and_the_ontology_on_the_configured_model(
    llm, support_ontology
):
    client, fake = llm
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case("kg", [CompetencyQuestion(id="happy", question="Are our customers happy?")])
    fake.requests.clear()

    client.evaluate("kg", 1)

    [request] = fake.requests
    assert request["model"] == "claude-test-model"
    assert "Are our customers happy?" in request["messages"][-1]["content"]
    system = "".join(block["text"] for block in request["system"])
    assert "Customer" in system and "OPENED" in system


def test_questions_with_a_concept_mapping_or_query_never_reach_the_llm(llm, support_ontology):
    client, fake = llm
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case(
        "kg",
        [
            CompetencyQuestion(id="a", question="Tickets?", concepts=("Ticket",)),
            CompetencyQuestion(id="b", question="Openers?", query="MATCH (c:Customer)-[:OPENED]->(t:Ticket) RETURN c"),
        ],
    )
    fake.requests.clear()

    client.evaluate("kg", 1)

    assert fake.requests == []


def test_the_mapper_that_produced_a_mapping_is_stored_with_the_result(llm, support_ontology):
    client, _ = llm
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case(
        "kg",
        [
            CompetencyQuestion(id="happy", question="Are our customers happy?"),
            CompetencyQuestion(id="tickets", question="Tickets?", concepts=("Ticket",)),
        ],
    )

    client.evaluate("kg", 1)
    questions = per_question(answerability(client.get_evaluation_results("kg", 1)))

    assert questions["happy"]["mapper"] == "anthropic:claude-test-model"
    assert "mapper" not in questions["tickets"]


def test_unusable_references_in_the_llm_answer_are_dropped(llm, support_ontology):
    client, _ = llm
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case("kg", [CompetencyQuestion(id="raised", question="Who raised which ticket?")])

    q = per_question(answerability(client.evaluate("kg", 1)))["raised"]

    assert q["required"] == ["(Customer)-[RAISED]->(Ticket)"]
    assert (q["status"], q["missing"]) == ("unanswerable", ["RAISED"])


@pytest.mark.parametrize(
    "question, error",
    [("Which tickets are urgent?", "model overloaded"), ("Write me a poem", "declined")],
)
def test_an_llm_failure_leaves_the_question_unmapped_without_blocking_versioning(
    llm, support_ontology, question, error
):
    client, _ = llm
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case("kg", [CompetencyQuestion(id="q", question=question)])

    version = client.register_ontology("kg", support_ontology.replace("OPENED", "RAISED"))
    q = per_question(answerability(client.get_evaluation_results("kg", version.number)))["q"]

    assert (q["status"], q["source"]) == ("unmapped", None)
    assert error in q["error"]


# --- configuration -----------------------------------------------------------------------

STUB_MAPPER_MODULE = '''
class StubMapper:
    description = "stub"

    def map_question(self, question, ontology):
        return ["Customer.name"]


instance = StubMapper()
'''


@pytest.fixture
def stub_mapper_module(tmp_path, monkeypatch):
    """An importable module `stub_mapper` with a deterministic mapper (class and instance)."""
    (tmp_path / "stub_mapper.py").write_text(STUB_MAPPER_MODULE)
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("spec", ["stub_mapper:StubMapper", "stub_mapper:instance"])
def test_local_mode_maps_with_the_mapper_named_in_the_environment(
    stub_mapper_module, monkeypatch, support_ontology, spec
):
    monkeypatch.setenv("STETIQ_QUESTION_MAPPER", spec)
    client = stetiq.Client(f"sqlite:///{stub_mapper_module / 'stetiq.db'}")
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case("kg", [CompetencyQuestion(id="q", question="Names?")])

    q = per_question(answerability(client.evaluate("kg", 1)))["q"]

    assert (q["status"], q["source"], q["mapper"]) == ("answerable", "model", "stub")


def test_without_a_configured_mapper_such_questions_stay_unmapped(
    tmp_path, monkeypatch, support_ontology
):
    monkeypatch.delenv("STETIQ_QUESTION_MAPPER", raising=False)
    client = stetiq.Client(f"sqlite:///{tmp_path / 'stetiq.db'}")
    client.create_knowledge_graph("kg", ontology=support_ontology)
    client.register_use_case("kg", [CompetencyQuestion(id="q", question="Names?")])

    assert per_question(answerability(client.evaluate("kg", 1)))["q"]["status"] == "unmapped"


def test_the_anthropic_mapper_takes_its_model_from_the_environment(monkeypatch):
    from stetiq.evaluation.llm_mapping import question_mapper_from_spec

    monkeypatch.delenv("STETIQ_QUESTION_MAPPER_MODEL", raising=False)
    assert question_mapper_from_spec("anthropic").description == "anthropic:claude-opus-5-5"
    monkeypatch.setenv("STETIQ_QUESTION_MAPPER_MODEL", "claude-sonnet-5-5")
    assert question_mapper_from_spec("anthropic").description == "anthropic:claude-sonnet-5-5"
    assert question_mapper_from_spec("none") is None
    with pytest.raises(ValueError, match="question mapper"):
        question_mapper_from_spec("no_such_module:Mapper")


def test_the_server_maps_with_the_mapper_given_on_the_command_line(
    stub_mapper_module, support_ontology
):
    import os
    import socket
    import subprocess
    import sys
    import time

    import httpx

    from stetiq.auth import TokenRegistry

    database_url = f"sqlite:///{stub_mapper_module / 'server.db'}"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(stub_mapper_module)}
    env.pop("STETIQ_QUESTION_MAPPER", None)
    proc = subprocess.Popen(
        [
            sys.executable, "-c", "from stetiq.cli import app; app()",
            "server", "--port", str(port), "--database-url", database_url,
            "--question-mapper", "stub_mapper:StubMapper",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            assert proc.poll() is None, proc.stderr.read().decode()
            assert time.monotonic() < deadline, "server did not start"
            try:
                if httpx.get(url + "/health").status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.1)
        _, token = TokenRegistry(database_url).issue("tester", {"*": "edit"})
        client = stetiq.Client(url, token=token)
        client.create_knowledge_graph("kg", ontology=support_ontology)
        client.register_use_case("kg", [CompetencyQuestion(id="q", question="Names?")])

        q = per_question(answerability(client.evaluate("kg", 1)))["q"]

        assert (q["source"], q["mapper"]) == ("model", "stub")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
