"""The plant-assistant showcase (showcase/plant-assistant) runs its show headless.

`run_show` is driven the way the stage runs it, with only the presenter left out: a
remote-mode `stetiq.Client` reaches an in-process stetiq server over REST with an API
token, and the upstream pipeline writes two real Neo4j Community servers, the
candidate graph every Construction Run builds and the production graph a deploy
replays a promoted run into. Extraction replays the committed llm-cache/; any call to
Claude fails the test.

The maintenance assistant (the GraphRAG Consumer) runs as its FastAPI app behind a
TestClient, with its own read-only stetiq token, and `run_show` reaches it only over its
HTTP API. Its Claude is a scripted fake replaying the committed recorded answers, so no
test calls a real LLM.

Needs Docker (two Neo4j testcontainers); with Docker up it runs, never skips."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import stetiq
from stetiq.auth import TokenRegistry
from stetiq.graph_source import Neo4jGraphSource
from stetiq.server import create_app
from stetiq.tracking import RemoteTrackingService

pytestmark = pytest.mark.neo4j

SHOWCASE_DIR = Path(__file__).resolve().parent.parent / "showcase" / "plant-assistant"
KG = "plant-maintenance"

V1_WORK_ORDERS = {
    ("WO-2031", "breakdown", "CNC-04"),
    ("WO-2032", "breakdown", "Press-02"),
    ("WO-2033", "preventive", "Weld-03"),
    ("WO-2034", "breakdown", "Paint-01"),
    ("WO-2035", "breakdown", "Conveyor-07"),
    ("WO-2036", "preventive", "CNC-04"),
    ("WO-2037", "breakdown", "Packer-05"),
    ("WO-2038", "breakdown", "Lathe-02"),
}
MACHINES = {"Press-02", "Weld-03", "Paint-01", "Packer-05", "Conveyor-07", "Lathe-02", "CNC-04"}
TECHNICIANS = {
    "Priya Natarajan",
    "Marcus Webb",
    "Lena Okafor",
    "Tomasz Nowak",
    "Aisha Rahman",
    "Diego Álvarez",
}


LINE_2 = "Why did Line 2's machines break down?"
SUPPLIERS = "Which suppliers' components keep failing?"


class FakeAnthropic:
    """Stands in for `anthropic.Anthropic()` in the assistant: answers `messages.create`
    from a script of {question, ontology_version, cypher, answer}. The request for Cypher
    (a structured-output request) gets the script's Cypher; the request for the answer
    gets its answer."""

    def __init__(self, script):
        self.script = script
        self.requests = []
        self.messages = self
        self.beta = SimpleNamespace(messages=self)

    def create(self, **request):
        self.requests.append(request)
        prompt = request["messages"][-1]["content"]
        for entry in self.script:
            on_version = f"Ontology Version {entry['ontology_version']}" in request["system"]
            if entry["question"] in prompt and on_version:
                wants_cypher = "format" in request.get("output_config", {})
                text = json.dumps({"cypher": entry["cypher"]}) if wants_cypher else entry["answer"]
                return SimpleNamespace(
                    stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)]
                )
        raise AssertionError(f"unexpected prompt: {prompt}")


def _recordings() -> list[dict]:
    return json.loads((SHOWCASE_DIR / "recordings" / "answers.json").read_text())["answers"]


def _no_claude(*args, **kwargs):
    raise AssertionError("the show called Claude; extraction must replay llm-cache/")


@pytest.fixture(scope="module")
def showcase():
    """The showcase's modules, imported from its folder, with Claude cut off."""
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(SHOWCASE_DIR))
        pipeline = importlib.import_module("plant_assistant.pipeline")
        mp.setattr(pipeline.ClaudeExtractor, "_call", _no_claude)
        yield importlib.import_module("show")


@pytest.fixture(scope="module")
def candidate(neo4j_container):
    with neo4j_container.get_driver() as driver:
        driver.execute_query("MATCH (n) DETACH DELETE n")
        yield driver


@pytest.fixture(scope="module")
def production(neo4j_second_container):
    with neo4j_second_container.get_driver() as driver:
        driver.execute_query("MATCH (n) DETACH DELETE n")
        yield driver


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The in-process stetiq server and its tracking database."""
    database_url = f"sqlite:///{tmp_path_factory.mktemp('stetiq') / 'server.db'}"
    with TestClient(create_app(database_url=database_url)) as http:
        yield http, database_url


def _remote(server, user: str, permission: str, **kwargs) -> stetiq.Client:
    http, database_url = server
    _, token = TokenRegistry(database_url).issue(user, {"*": permission})
    return stetiq.Client(
        str(http.base_url),
        service=RemoteTrackingService(str(http.base_url), http=http, token=token),
        **kwargs,
    )


@pytest.fixture(scope="module")
def client(server, candidate):
    """A remote-mode client: stetiq is reached over REST with an API token, and the
    Graph Source it observes is the candidate graph."""
    return _remote(server, "ci-bot", "edit", graph_source=Neo4jGraphSource(candidate))


@pytest.fixture(scope="module")
def assistant_module(showcase):
    return importlib.import_module("plant_assistant.assistant")


def _assistant_http(assistant_module, server, production, llm):
    """The maintenance assistant's app, reading stetiq with its own read-only token and
    answering from the production graph."""
    assistant = assistant_module.Assistant(
        _remote(server, "maintenance-assistant", "read"), production, llm=llm
    )
    return TestClient(assistant_module.create_app(assistant, poll_interval=None))


@pytest.fixture(scope="module")
def claude():
    """The assistant's Claude: replays the recorded answers, plus one question whose
    Cypher would delete the work orders."""
    return FakeAnthropic(
        [
            *_recordings(),
            {
                "question": "Clean up the old work orders",
                "ontology_version": 1,
                "cypher": "MATCH (w:WorkOrder) DETACH DELETE w",
                "answer": "Done.",
            },
        ]
    )


@pytest.fixture(scope="module")
def assistant(assistant_module, server, production, claude):
    with _assistant_http(assistant_module, server, production, claude) as http:
        yield http


@pytest.fixture(scope="module")
def show(showcase, client, candidate, production, assistant):
    return showcase.run_show(
        client,
        showcase.Graphs(candidate=candidate, production=production),
        assistant=assistant,
        quiet=True,
    )


def _work_orders(driver) -> set[tuple[str, str, str]]:
    records, _, _ = driver.execute_query(
        "MATCH (w:WorkOrder)-[:PERFORMED_ON]->(m:Machine) RETURN w.id AS id, w.kind AS kind, "
        "m.name AS machine"
    )
    return {(r["id"], r["kind"], r["machine"]) for r in records}


def _names(driver, label: str) -> set[str]:
    records, _, _ = driver.execute_query(f"MATCH (n:{label}) RETURN n.name AS name")
    return {r["name"] for r in records}


def _faulted_orders(driver) -> set[str]:
    records, _, _ = driver.execute_query(
        "MATCH (w:WorkOrder)-[:CAUSED_BY]->(:Fault) RETURN DISTINCT w.id AS id"
    )
    return {r["id"] for r in records}


def test_act_0_promotes_v1_and_deploys_it(show):
    assert show.acts[0].line == "v1   Gate ✅   promoted: production -> v1   deployed"


def test_production_holds_v1s_work_orders_machines_technicians_and_faults(show, production):
    assert _work_orders(production) == V1_WORK_ORDERS
    assert _names(production, "Machine") == MACHINES
    assert _names(production, "Technician") == TECHNICIANS
    assert _faulted_orders(production) == {wo for wo, _, _ in V1_WORK_ORDERS}


def test_the_candidate_graph_holds_the_run_stetiq_observed(show, client, candidate):
    run = client.get_run(show.acts[0].run.id)
    assert (run.status, run.ontology_version, run.candidate_version) == ("finished", 1, None)
    assert _work_orders(candidate) == V1_WORK_ORDERS
    assert _names(candidate, "Technician") == TECHNICIANS
    # The executed Competency Questions ran as real Cypher on the candidate graph.
    [execution] = [
        r
        for r in client.get_run_evaluation_results(run.id)
        if r.evaluator == "competency_question_execution"
    ]
    rows = {d.item: d.data["rows"] for d in execution.details if d.data}
    assert rows["breakdown-technicians"] == 6
    assert rows["downstream-of-press"] == 3
    # The assistant's briefing question, the baseline its Consumer Gate compares with.
    assert rows["breakdown-causes"] == 6


def test_production_is_promoted_to_v1_then_to_v3_only(show, client):
    production = [
        (p.from_version, p.to_version)
        for p in client.list_promotions(KG)
        if p.alias == "production"
    ]
    assert [to for _, to in production] == [1, 3]


def test_a_cache_miss_is_an_error_naming_live_and_record(showcase, tmp_path):
    pipeline = importlib.import_module("plant_assistant.pipeline")
    extractor = pipeline.ClaudeExtractor("v1", mode="replay", cache_dir=tmp_path)
    [report, *_] = pipeline.read_reports()
    context = pipeline.Context(machines=(), technicians=(), run_context="")

    with pytest.raises(pipeline.CacheMissError) as raised:
        extractor.extract(report, context)

    assert "--live" in str(raised.value)
    assert "--record" in str(raised.value)


# --- The maintenance assistant on v1 ---------------------------------------------------


def test_act_0_the_assistant_is_on_v1(show):
    assert show.acts[0].banner == "on Ontology v1"


def test_act_0_line_2_broke_down_on_cnc_04_and_lathe_02(show):
    answer = show.acts[0].answers[LINE_2]
    assert (answer.ontology_version, answer.source) == (1, "live")
    assert "kind = 'breakdown'" in answer.cypher
    assert answer.work_orders == ["WO-2031", "WO-2038"]
    for named in ("WO-2031", "CNC-04", "WO-2038", "Lathe-02"):
        assert named in answer.answer


def test_act_0_the_graph_does_not_record_suppliers(show):
    answer = show.acts[0].answers[SUPPLIERS]
    assert answer.ontology_version == 1
    assert "does not record suppliers" in answer.answer
    assert answer.work_orders == []


def test_claudes_prompt_carries_the_ontology_version_fetched_from_stetiq(show, client, claude):
    from_stetiq = client.get_ontology_yaml(KG, 1)
    # The local file's opening comment: only the file has it, stetiq's YAML does not.
    [opening, *_] = (SHOWCASE_DIR / "ontology" / "v1.yaml").read_text().splitlines()
    assert claude.requests
    for request in claude.requests:
        assert request["model"] == "claude-sonnet-5-5"
        assert from_stetiq in request["system"]
        assert opening not in request["system"]


def test_generated_cypher_runs_read_only(show, assistant, production):
    response = assistant.post("/api/ask", json={"question": "Clean up the old work orders"})

    assert response.status_code == 422
    assert "read-only" in response.json()["detail"]
    assert _work_orders(production) == V1_WORK_ORDERS


def test_without_an_api_key_scripted_questions_answer_from_recordings(
    show, assistant_module, server, production
):
    # Started after the show, it takes the version `production` points to then: v3.
    with _assistant_http(assistant_module, server, production, None) as offline:
        status = offline.get("/api/status").json()
        line_2 = offline.post("/api/ask", json={"question": LINE_2})
        suppliers = offline.post("/api/ask", json={"question": SUPPLIERS})
        free_form = offline.post("/api/ask", json={"question": "Which machine is the oldest?"})

    assert (status["in_use"], status["free_form"]) == (3, False)
    assert "ANTHROPIC_API_KEY" in status["message"]
    assert line_2.status_code == 200
    assert (line_2.json()["source"], line_2.json()["ontology_version"]) == ("recorded", 3)
    assert line_2.json()["work_orders"] == ["WO-2031", "WO-2038"]
    # The recorded Cypher runs on the production graph: the work orders come from its rows.
    assert set(suppliers.json()["work_orders"]) == {
        "WO-2031",
        "WO-2032",
        "WO-2036",
        "WO-2037",
        "WO-2038",
    }
    assert "SKF" in suppliers.json()["answer"]
    assert free_form.status_code == 503
    assert "ANTHROPIC_API_KEY" in free_form.json()["detail"]


def test_the_chat_page_shows_the_banner_and_the_cypher(assistant):
    page = assistant.get("/")
    assert page.status_code == 200
    assert 'id="banner"' in page.text
    assert "a.cypher" in page.text


# --- Act 2: prompt v2 with stetiq, Act 3: the fix ---------------------------------------


def test_act_2_passes_the_gate_and_fails_both_consumers_and_stays_unpromoted(show):
    assert show.acts[2].line == (
        "prompt v2   Gate ✅   Consumer Gate ❌ (maintenance-assistant ❌ breakdown-causes "
        "6 → 4, −33%; reliability-dashboard ❌ breakdown-technicians 6 → 4, −33%)   "  # noqa: RUF001 - the minus sign stetiq writes
        "not promoted (Candidate stays at v2)"
    )


def test_act_2_fails_the_assistants_briefing_gate_on_line_2s_breakdowns(show):
    [assistant] = [c for c in show.acts[2].consumer_gates if c.consumer == "maintenance-assistant"]
    [briefing] = [o for o in assistant.outcomes if o.gate.name == "briefing-rows-hold"]
    [finding] = briefing.findings
    assert (finding.task, finding.competency_question) == (
        "brief-shift-lead",
        "breakdown-causes",
    )
    assert (finding.before, finding.after, finding.limit) == (6, 4, 0.10)


def test_act_2_leaves_production_on_v1_and_its_graph_alone(show, client):
    act = show.acts[2]
    assert (act.promoted, act.deployed) == (False, False)
    assert act.production_run == show.acts[0].run.id
    assert act.run.candidate_version == 2
    production = [p.to_version for p in client.list_promotions(KG) if p.alias == "production"]
    assert 2 not in production


def test_act_2s_candidate_answers_the_suppliers_question(show, client):
    [execution] = [
        r
        for r in client.get_run_evaluation_results(show.acts[2].run.id)
        if r.evaluator == "competency_question_execution"
    ]
    rows = {d.item: d.data["rows"] for d in execution.details if d.data}
    assert rows["parts-suppliers"] == 5


def test_act_3_the_fix_passes_both_gates_is_promoted_to_v3_and_deployed(show):
    assert show.acts[3].line == (
        "fix   Gate ✅   Consumer Gate ✅   promoted: production -> v3   deployed"
    )


def test_act_3s_diff_gate_accepts_the_vocabulary_binding_on_evidence(show):
    [diff_gate] = [o for o in show.acts[3].gates.outcomes if o.gate.name == "no-breaking-changes"]
    assert diff_gate.passed
    assert diff_gate.reasons == (
        "binding WorkOrder.kind -> WorkOrderKind accepted: all observed values are in the "
        "Vocabulary",
    )


def test_act_3_moves_production_to_v3_and_redeploys_its_graph(show, client, production):
    act = show.acts[3]
    assert act.production_run == act.run.id
    assert client.get_contract_version(KG).number == 3
    promotions = [(p.from_version, p.to_version) for p in client.list_promotions(KG)]
    assert promotions[-1] == (1, 3)
    # Line 2's two breakdowns are breakdowns again, and the suppliers are in.
    assert _work_orders(production) == V1_WORK_ORDERS
    assert _names(production, "Supplier")


def test_both_consumers_have_their_verdicts_recorded_for_v2_and_v3(show, client):
    verdicts = {
        (r.consumer, version, r.passed)
        for version in (2, 3)
        for r in client.list_consumer_gate_results(KG, version=version)
    }
    assert verdicts == {
        ("maintenance-assistant", 2, False),
        ("reliability-dashboard", 2, False),
        ("maintenance-assistant", 3, True),
        ("reliability-dashboard", 3, True),
    }
