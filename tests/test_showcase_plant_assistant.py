"""The plant-assistant showcase (showcase/plant-assistant) runs its show headless.

`run_show` is driven the way the stage runs it, with only the presenter left out: a
remote-mode `stetiq.Client` reaches an in-process stetiq server over REST with an API
token, and the upstream pipeline writes two real Neo4j Community servers, the
candidate graph every Construction Run builds and the production graph a deploy
replays a promoted run into. Extraction replays the committed llm-cache/; any call to
Claude fails the test.

The maintenance assistant (the GraphRAG Consumer) runs as its FastAPI app behind a
TestClient, with its own read-only stetiq token, and `run_show` reaches it only over its
HTTP API. Its Claude is a scripted fake replaying the committed answers, which were
written by hand (`recordings/answers.json`), so no test calls a real LLM.

The show plays Acts 0 and 1 without stetiq (the assistant's guard off, every run
deployed), rewinds stetiq, both graphs and the assistant, then plays Acts 0, 2 and 3
with stetiq; the tests pin both passes. Where the stage's rewind recreates the stetiq
service's volume through docker compose, the test's starts a fresh in-process server
with new tokens (`Tracking.rewind`): the one place stage and test differ. The `--act N`
tests come last, since they rewind again.

Needs Docker (two Neo4j testcontainers), and skips only when Docker is unavailable."""

import contextlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import neo4j
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


class Tracking:
    """The stetiq server the show reaches, in-process. `rewind` starts a fresh one (a new
    SQLite database, new tokens), as compose recreates the stetiq service's volume on
    stage; gives each registered assistant a client with its new read token, as the
    assistant's restart does; and returns the show's new edit client."""

    def __init__(self, directory: Path, candidate) -> None:
        self.directory = directory
        self.candidate = candidate
        self.assistants = []
        self.servers = 0
        self._stack = contextlib.ExitStack()
        self.rewind()

    def rewind(self) -> stetiq.Client:
        self._stack.close()
        self.servers += 1
        self.database_url = f"sqlite:///{self.directory / f'server-{self.servers}.db'}"
        app = create_app(database_url=self.database_url)
        self.http = self._stack.enter_context(TestClient(app))
        for assistant in self.assistants:
            assistant.stetiq = self.remote("maintenance-assistant", "read")
        self.client = self.remote("ci-bot", "edit", graph_source=Neo4jGraphSource(self.candidate))
        return self.client

    def remote(self, user: str, permission: str, **kwargs) -> stetiq.Client:
        """A remote-mode client of the current server, with a token of its own."""
        return _remote(self.http, self.database_url, user, permission, **kwargs)

    def close(self) -> None:
        self._stack.close()


def _remote(http, database_url: str, user: str, permission: str, **kwargs) -> stetiq.Client:
    _, token = TokenRegistry(database_url).issue(user, {"*": permission})
    return stetiq.Client(
        str(http.base_url),
        service=RemoteTrackingService(str(http.base_url), http=http, token=token),
        **kwargs,
    )


@pytest.fixture(scope="module")
def tracking(tmp_path_factory, candidate):
    """The in-process stetiq server, which a rewind replaces with a fresh one."""
    tracking = Tracking(tmp_path_factory.mktemp("stetiq"), candidate)
    yield tracking
    tracking.close()


@pytest.fixture
def client(show, tracking):
    """After the show: a remote-mode client of the server the last rewind started, whose
    Graph Source is the candidate graph."""
    return tracking.client


@pytest.fixture(scope="module")
def assistant_module(showcase):
    return importlib.import_module("plant_assistant.assistant")


def _assistant_app(assistant_module, stetiq_client, production, llm):
    """The maintenance assistant's app, reading stetiq with `stetiq_client` (its own
    read-only token) and answering from the production graph."""
    assistant = assistant_module.Assistant(stetiq_client, production, llm=llm)
    return assistant, TestClient(assistant_module.create_app(assistant, poll_interval=None))


@pytest.fixture(scope="module")
def claude():
    """The assistant's Claude: replays the hand-written answers, plus one question whose
    Cypher would delete the work orders (asked after the show, on v3)."""
    return FakeAnthropic(
        [
            *_recordings(),
            {
                "question": "Clean up the old work orders",
                "ontology_version": 3,
                "cypher": "MATCH (w:WorkOrder) DETACH DELETE w",
                "answer": "Done.",
            },
        ]
    )


@pytest.fixture(scope="module")
def assistant(assistant_module, tracking, production, claude):
    """The show's assistant: each rewind gives it a client with its new token."""
    state, app = _assistant_app(
        assistant_module, tracking.remote("maintenance-assistant", "read"), production, claude
    )
    tracking.assistants.append(state)
    with app as http:
        yield http


@pytest.fixture(scope="module")
def graphs(showcase, candidate, production):
    return showcase.Graphs(candidate=candidate, production=production)


def _run_show(showcase, tracking, graphs, assistant, **kwargs):
    return showcase.run_show(
        graphs, rewind=tracking.rewind, assistant=assistant, **{"quiet": True, **kwargs}
    )


@pytest.fixture(scope="module")
def show(showcase, tracking, graphs, assistant):
    """The whole show: Acts 0 and 1 without stetiq, the rewind, then Acts 0, 2 and 3."""
    return _run_show(showcase, tracking, graphs, assistant)


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
    # The local file's opening comment: only the file has it, stetiq's YAML does not.
    [opening, *_] = (SHOWCASE_DIR / "ontology" / "v1.yaml").read_text().splitlines()
    assert claude.requests
    for request in claude.requests:
        [version] = {v for v in (1, 2, 3) if f"Ontology Version {v}" in request["system"]}
        assert request["model"] == "claude-sonnet-5-5"
        assert client.get_ontology_yaml(KG, version) in request["system"]
        assert opening not in request["system"]


def test_generated_cypher_runs_read_only(show, assistant, production):
    response = assistant.post("/api/ask", json={"question": "Clean up the old work orders"})

    assert response.status_code == 422
    assert "read-only" in response.json()["detail"]
    assert _work_orders(production) == V1_WORK_ORDERS


def test_without_an_api_key_scripted_questions_answer_from_hand_written_answers(
    show, assistant_module, tracking, production
):
    # Started after the show, it takes the version `production` points to then: v3.
    reader = tracking.remote("maintenance-assistant", "read")
    _, app = _assistant_app(assistant_module, reader, production, None)
    with app as offline:
        status = offline.get("/api/status").json()
        line_2 = offline.post("/api/ask", json={"question": LINE_2})
        suppliers = offline.post("/api/ask", json={"question": SUPPLIERS})
        free_form = offline.post("/api/ask", json={"question": "Which machine is the oldest?"})

    assert (status["in_use"], status["free_form"]) == (3, False)
    assert "ANTHROPIC_API_KEY" in status["message"]
    assert line_2.status_code == 200
    assert (line_2.json()["source"], line_2.json()["ontology_version"]) == ("scripted", 3)
    assert line_2.json()["work_orders"] == ["WO-2031", "WO-2038"]
    # The scripted Cypher runs on the production graph: the work orders come from its rows.
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


# --- Act 1: prompt v2 without stetiq ---------------------------------------------------


def test_act_1_deploys_prompt_v2_without_gates(show):
    assert show.acts[1].line == "prompt v2   tests ✅   deployed"


def test_act_1_the_guard_is_off_and_the_assistant_follows_v2(show):
    status = show.acts[1].status
    assert show.acts[1].banner == "on Ontology v2"
    assert (status["in_use"], status["guard"], status["decision"]) == (2, "off", None)


def test_act_1_on_v2_the_suppliers_question_answers(show):
    answer = show.acts[1].answers[SUPPLIERS]
    assert answer.ontology_version == 2
    assert "SKF" in answer.answer
    assert set(answer.work_orders) == {"WO-2031", "WO-2032", "WO-2036", "WO-2037", "WO-2038"}


def test_act_1_on_v2_line_2_had_no_breakdowns_from_mondays_cypher(show):
    answer = show.acts[1].answers[LINE_2]
    monday = show.without_stetiq[0].answers[LINE_2]
    assert answer.ontology_version == 2
    assert answer.answer.startswith("Line 2 had no breakdowns.")
    assert answer.cypher == monday.cypher
    assert "kind = 'breakdown'" in answer.cypher
    assert answer.work_orders == []


def test_the_first_pass_act_0_is_monday_on_v1(show):
    act = show.without_stetiq[0]
    assert act.line == "v1   Gate ✅   promoted: production -> v1   deployed"
    assert act.banner == "on Ontology v1"
    assert act.status["guard"] == "off"
    assert act.answers[LINE_2].work_orders == ["WO-2031", "WO-2038"]


def test_after_the_rewind_act_2_starts_from_v1_in_production_with_the_guard_on(show, client):
    status = show.acts[0].status
    assert (status["in_use"], status["guard"], status["offered"]) == (1, "on", None)
    # The rewind left no trace of Act 1 in stetiq: one Construction Run per act since.
    runs = {r.id for r in client.list_runs(KG)}
    assert runs == {show.acts[n].run.id for n in (0, 2, 3)}
    assert show.acts[1].run.id not in runs


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


# --- The Connector guard ----------------------------------------------------------------


def test_act_2_the_guard_refuses_v2_naming_the_symptom(show):
    assert show.acts[2].banner == "on Ontology v1 · v2 offered: refused (breakdown-causes −33%)"  # noqa: RUF001 - the minus sign stetiq writes


def test_act_2_the_status_reports_v1_in_use_and_v2_refused(show):
    status = show.acts[2].status
    assert (status["in_use"], status["offered"], status["decision"]) == (1, 2, "refused")
    assert status["reason"] == "breakdown-causes −33%"  # noqa: RUF001 - the minus sign stetiq writes


def test_act_2_while_v2_is_refused_line_2_still_broke_down_on_cnc_04_and_lathe_02(show):
    answer = show.acts[2].answers[LINE_2]
    assert answer.ontology_version == 1
    assert answer.work_orders == ["WO-2031", "WO-2038"]
    for named in ("WO-2031", "CNC-04", "WO-2038", "Lathe-02"):
        assert named in answer.answer


def test_act_2_while_v2_is_refused_the_graph_still_does_not_record_suppliers(show):
    answer = show.acts[2].answers[SUPPLIERS]
    assert answer.ontology_version == 1
    assert "does not record suppliers" in answer.answer


def test_act_3_the_guard_accepts_v3_within_one_poll(show):
    assert show.acts[3].banner == "on Ontology v3 · accepted"
    status = show.acts[3].status
    assert (status["in_use"], status["offered"], status["decision"]) == (3, 3, "accepted")


def test_act_3_on_v3_line_2s_breakdowns_and_the_suppliers_both_answer(show):
    line_2, suppliers = show.acts[3].answers[LINE_2], show.acts[3].answers[SUPPLIERS]
    assert (line_2.ontology_version, suppliers.ontology_version) == (3, 3)
    assert line_2.work_orders == ["WO-2031", "WO-2038"]
    for named in ("WO-2031", "CNC-04", "WO-2038", "Lathe-02"):
        assert named in line_2.answer
    assert "SKF" in suppliers.answer
    assert set(suppliers.work_orders) == {"WO-2031", "WO-2032", "WO-2036", "WO-2037", "WO-2038"}


def test_the_chat_page_shows_the_guards_banner(assistant):
    assert "s.banner" in assistant.get("/").text


@pytest.fixture
def unjudged(tmp_path):
    """A second stetiq server: `production` on v1, and v2 registered but never built, so
    no Consumer Gate verdict exists for it."""
    database_url = f"sqlite:///{tmp_path / 'unjudged.db'}"
    with TestClient(create_app(database_url=database_url)) as http:
        owner = _remote(http, database_url, "owner", "edit")
        owner.create_knowledge_graph(KG, ontology=SHOWCASE_DIR / "ontology" / "v1.yaml")
        owner.set_alias(KG, "production", 1)
        owner.register_ontology(KG, SHOWCASE_DIR / "ontology" / "fix.yaml")
        yield http, database_url, owner


def _fresh_assistant(assistant_module, http, database_url, production):
    """The assistant, without Claude, on the `unjudged` server."""
    reader = _remote(http, database_url, "maintenance-assistant", "read")
    _, app = _assistant_app(assistant_module, reader, production, None)
    return app


def test_a_version_with_no_recorded_verdict_is_refused_not_taken(
    unjudged, assistant_module, production
):
    http, database_url, owner = unjudged
    with _fresh_assistant(assistant_module, http, database_url, production) as fresh:
        offered = fresh.post("/api/poll").json()
        owner.set_alias(KG, "production", 2)  # deployed, but still without a verdict
        deployed = fresh.post("/api/poll").json()

    for status in (offered, deployed):
        assert (status["in_use"], status["offered"], status["decision"]) == (1, 2, "refused")
        assert status["reason"] == "no Consumer Gate verdict"
        assert status["banner"] == (
            "on Ontology v1 · v2 offered: refused (no Consumer Gate verdict)"
        )


def test_with_the_guard_off_the_newest_version_is_taken_without_a_verdict(
    unjudged, assistant_module, production
):
    http, database_url, _ = unjudged
    with _fresh_assistant(assistant_module, http, database_url, production) as fresh:
        guarded = fresh.post("/api/poll").json()
        off = fresh.post("/api/reset", json={"guard": "off"}).json()
        followed = fresh.post("/api/poll").json()
        back_on = fresh.post("/api/reset", json={"guard": "on"}).json()
        restarted = fresh.post("/api/poll").json()

    assert (guarded["in_use"], guarded["decision"]) == (1, "refused")
    assert (off["in_use"], off["guard"], off["banner"]) == (None, "off", "no Ontology Version yet")
    assert (followed["in_use"], followed["offered"], followed["decision"]) == (2, None, None)
    assert followed["banner"] == "on Ontology v2"
    assert back_on["in_use"] is None
    # Back on, it starts over as on startup: it takes the version `production` points to.
    assert (restarted["in_use"], restarted["guard"]) == (1, "on")


# --- On stage: the stack check, the presenter's pauses, the epilogue --------------------


def test_a_container_that_is_down_is_named_before_the_act_starts(
    show, showcase, tracking, client, candidate, assistant
):
    runs_before = {r.id for r in client.list_runs(KG)}
    with neo4j.GraphDatabase.driver("bolt://localhost:1", auth=("neo4j", "x")) as stopped:
        graphs = showcase.Graphs(candidate=candidate, production=stopped)
        with pytest.raises(showcase.StackDown) as raised:
            showcase.run_show(
                graphs,
                rewind=lambda: pytest.fail("the show rewound with a container down"),
                assistant=assistant,
                quiet=True,
                check=showcase.stack_check(
                    stetiq=tracking.http, graphs=graphs, assistant=assistant
                ),
            )

    assert raised.value.down == ["graph-production"]
    assert "graph-production is down" in str(raised.value)
    assert "docker compose up -d graph-production" in str(raised.value)
    assert {r.id for r in client.list_runs(KG)} == runs_before


def test_the_stack_check_names_nothing_when_every_container_is_up(
    showcase, tracking, graphs, assistant
):
    check = showcase.stack_check(stetiq=tracking.http, graphs=graphs, assistant=assistant)
    assert check() == []


def test_non_interactive_pauses_never_wait_for_enter(showcase):
    def no_terminal(prompt):
        raise AssertionError(f"waited for Enter: {prompt}")

    showcase.presenter_pause(interactive=False, read=no_terminal)("Act 1, without stetiq")


def test_interactive_pauses_wait_for_enter_and_carry_on_when_input_ends(showcase):
    prompts = []
    showcase.presenter_pause(interactive=True, read=prompts.append)("Act 1, without stetiq")

    def ended(prompt):
        raise EOFError

    showcase.presenter_pause(interactive=True, read=ended)("Act 2, with stetiq")
    assert len(prompts) == 1
    assert "Enter" in prompts[0]
    assert "Act 1, without stetiq" in prompts[0]


@pytest.fixture(scope="module")
def epilogue(show, showcase, tracking, production):
    """After the show: the hand edit to the production graph, then its Observation."""
    observer = tracking.remote("ops", "edit", graph_source=Neo4jGraphSource(production))
    return showcase.run_epilogue(observer, production, quiet=True)


def test_the_epilogue_hand_edit_adds_spare_parts_and_deletes_the_done_follow_ups(
    epilogue, production
):
    assert (epilogue.spare_parts_added, epilogue.follow_ups_deleted) == (3, 6)
    assert len(_names(production, "SparePart")) == 3
    records, _, _ = production.execute_query(
        "MATCH (f:FollowUp) RETURN f.status AS status, count(*) AS n"
    )
    assert {r["status"]: r["n"] for r in records} == {"open": 6}


def test_the_epilogue_records_drift_against_production(epilogue, client):
    drift = epilogue.outcome.drift
    assert drift is not None
    assert (drift.contract_alias, drift.ontology_version) == ("production", 3)
    assert {(f.kind.value, f.subject) for f in drift.structural} == {
        ("undeclared", "SparePart"),
        ("undeclared", "SparePart.name"),
        ("undeclared", "SparePart.stock"),
    }
    # Against the previous Observation (Act 3's run), beyond max_count_drop 0.25.
    assert {
        (f.kind.value, f.subject, f.previous_count, f.observed_count) for f in drift.statistical
    } == {
        ("count_drop", "FollowUp", 12, 6),
        ("count_drop", "HAS_FOLLOW_UP", 12, 6),
        ("count_drop", "ASSIGNED_TO", 20, 14),
        ("count_drop", "(FollowUp)-[ASSIGNED_TO]->(Technician)", 12, 6),
        ("count_drop", "(WorkOrder)-[HAS_FOLLOW_UP]->(FollowUp)", 12, 6),
    }
    assert drift.id in {e.id for e in client.list_drift_events(KG)}
    assert epilogue.line == (
        "hand edit: +3 SparePart, −6 done FollowUp   Drift ⚠ against production -> v3 "  # noqa: RUF001 - the minus sign the show writes
        "(3 structural, 5 statistical)"
    )


# --- --act N: the show from the beginning of an act -----------------------------------
# Last in the module: these rewind stetiq and both graphs, which the tests above read.


@pytest.mark.parametrize("start_act", [2, 3])
def test_starting_at_an_act_reaches_the_state_the_acts_before_it_leave(
    start_act, show, showcase, tracking, graphs, production, assistant
):
    servers = tracking.servers
    beats = []
    resumed = _run_show(
        showcase,
        tracking,
        graphs,
        assistant,
        start_act=start_act,
        quiet=False,
        pause=beats.append,
    )
    client = tracking.client

    for n in (0, 2, 3):
        assert resumed.acts[n].line == show.acts[n].line
        assert resumed.acts[n].banner == show.acts[n].banner
    assert resumed.without_stetiq == []
    # One rewind, to a fresh server that holds only the runs the show replayed since.
    assert tracking.servers == servers + 1
    assert {r.id for r in client.list_runs(KG)} == {resumed.acts[n].run.id for n in (0, 2, 3)}
    # The presenter is paused only at the beats the audience sees: each act it plays, and
    # each scripted question in it; the acts replayed before it pass without a pause.
    played = {2: ["Act 2, with stetiq"], 3: []}[start_act] + ["Act 3, the fix"]
    assert [b for b in beats if b.startswith("Act")] == played
    assert [b for b in beats if not b.startswith("Act")] == [
        f"ask: {q}" for _ in played for q in (LINE_2, SUPPLIERS)
    ]
    # The Act 2 the show starts from (or replays) left production on v1 and its graph.
    assert resumed.acts[2].status["in_use"] == 1
    assert resumed.acts[2].production_run == resumed.acts[0].run.id
    assert client.get_contract_version(KG).number == 3
    assert _work_orders(production) == V1_WORK_ORDERS


def test_a_version_whose_verdict_passed_waits_until_production_points_to_it(
    show, showcase, tracking, graphs, assistant
):
    # Acts 0 and 2 from a rewind, then the fix's CI up to its verdicts, stopping short of
    # the Promotion: v3 has passed the assistant's Consumer Gate, `production` is on v1.
    replay = showcase.Show(
        graphs, rewind=tracking.rewind, extraction="replay", quiet=True, assistant=assistant
    )
    replay.rewind(guard="on")
    replay.play_act(0, replay.act_0, quiet=True)
    replay.play_act(2, replay.act_2, quiet=True)
    fix = replay.client.register_ontology(KG, SHOWCASE_DIR / "ontology" / "fix.yaml")
    run = replay.construct("fix", ontology_version=fix.number)
    verdicts = {c.consumer: c.passed for c in replay.client.evaluate_consumer_gates(KG, run=run.id)}

    status = assistant.post("/api/poll").json()
    answer = assistant.post("/api/ask", json={"question": LINE_2}).json()

    assert verdicts["maintenance-assistant"] is True
    assert replay.client.get_contract_version(KG).number == 1
    assert (status["in_use"], status["offered"], status["decision"]) == (1, 3, "waiting")
    assert status["banner"] == (
        "on Ontology v1 · v3 offered: waiting (Consumer Gate passed, not in production yet)"
    )
    assert answer["ontology_version"] == 1
