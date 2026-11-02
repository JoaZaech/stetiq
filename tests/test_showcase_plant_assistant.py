"""The plant-assistant showcase (showcase/plant-assistant) runs its show headless.

`run_show` is driven the way the stage runs it, with only the presenter left out: a
remote-mode `stetiq.Client` reaches an in-process stetiq server over REST with an API
token, and the upstream pipeline writes two real Neo4j Community servers, the
candidate graph every Construction Run builds and the production graph a deploy
replays a promoted run into. Extraction replays the committed llm-cache/; any call to
Claude fails the test.

Needs Docker (two Neo4j testcontainers); with Docker up it runs, never skips."""

import importlib
from pathlib import Path

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
def client(tmp_path_factory, candidate):
    """A remote-mode client: stetiq is reached over REST with an API token, and the
    Graph Source it observes is the candidate graph."""
    database_url = f"sqlite:///{tmp_path_factory.mktemp('stetiq') / 'server.db'}"
    _, token = TokenRegistry(database_url).issue("ci-bot", {"*": "edit"})
    with TestClient(create_app(database_url=database_url)) as http:
        yield stetiq.Client(
            str(http.base_url),
            service=RemoteTrackingService(str(http.base_url), http=http, token=token),
            graph_source=Neo4jGraphSource(candidate),
        )


@pytest.fixture(scope="module")
def show(showcase, client, candidate, production):
    return showcase.run_show(
        client, showcase.Graphs(candidate=candidate, production=production), quiet=True
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


def test_production_is_promoted_to_v1(show, client):
    assert client.get_contract_version(KG).number == 1


def test_a_cache_miss_is_an_error_naming_live_and_record(showcase, tmp_path):
    pipeline = importlib.import_module("plant_assistant.pipeline")
    extractor = pipeline.ClaudeExtractor("v1", mode="replay", cache_dir=tmp_path)
    [report, *_] = pipeline.read_reports()
    context = pipeline.Context(machines=(), technicians=(), run_context="")

    with pytest.raises(pipeline.CacheMissError) as raised:
        extractor.extract(report, context)

    assert "--live" in str(raised.value)
    assert "--record" in str(raised.value)
