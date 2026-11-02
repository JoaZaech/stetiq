"""Consumer Gates: per-Consumer rules declared in the Use Case, evaluated by the server
against the Contract Alias baseline, recorded, and enforced in CI by `stetiq consumer gate`.

The executed Competency Questions of each Construction Run return the rows the test
sets with `add_query_result`, so each run's row counts are what the test says."""

import os

import pytest
import yaml
from typer.testing import CliRunner

import stetiq
from stetiq import (
    ConflictingArgumentsError,
    ConsumerGateConfigError,
    NoConsumerGatesError,
    NotFoundError,
)
from stetiq.cli import CONSUMER_GATE_FAILED_EXIT_CODE, app
from stetiq.graph_source import GraphSourceScope, InMemoryGraphSource
from stetiq.tracking import SqlStore
from stetiq.use_case import RowCountDropGate, canonicalize, parse_use_case_yaml, to_dict

KG = "plant"

ONTOLOGY = """
node_types:
  - label: Machine
  - label: WorkOrder
relationship_types:
  - label: PERFORMED_ON
patterns:
  - [WorkOrder, PERFORMED_ON, Machine]
"""

TECHNICIANS = "MATCH (w:WorkOrder {kind: 'breakdown'}) RETURN w"
DOWNTIME = "MATCH (w:WorkOrder) RETURN w.kind, count(*)"
MACHINES = "MATCH (m:Machine) RETURN m"

USE_CASE = f"""
competency_questions:
  - id: breakdown-technicians
    question: Which technicians fixed breakdowns?
    query: "{TECHNICIANS}"
  - id: downtime-by-kind
    question: How much downtime per kind of work order?
    query: "{DOWNTIME}"
  - id: machines
    question: Which machines are there?
    query: "{MACHINES}"
  - id: spare-parts
    question: Which spare parts does a machine need?
consumers:
  - id: reliability-dashboard
    name: Reliability dashboard
    tasks:
      - id: triage-breakdowns
        description: Triage breakdowns
        competency_questions: [breakdown-technicians, downtime-by-kind]
    consumer_gates:
      - name: triage-rows-hold
        check: row_count_drop
        task: triage-breakdowns
        max_drop: 0.10
  - id: maintenance-assistant
    name: Maintenance assistant
    tasks:
      - id: list-machines
        description: List the machines
        competency_questions: [machines]
    consumer_gates:
      - check: row_count_drop
        task: list-machines
        max_drop: 0.5
  - id: safety-team
    name: Safety team
    tasks:
      - id: audit
        description: Audit the plant
        competency_questions: [machines]
"""


def use_case_with(**gates_by_consumer):
    """USE_CASE with the `consumer_gates` of the named Consumers replaced."""
    data = yaml.safe_load(USE_CASE)
    for consumer in data["consumers"]:
        if consumer["id"] in gates_by_consumer:
            consumer["consumer_gates"] = gates_by_consumer[consumer["id"]]
    return data


# --- Declaring Consumer Gates in the Use Case ------------------------------------------


def test_a_consumer_declares_consumer_gates_in_the_use_case():
    use_case = parse_use_case_yaml(USE_CASE)

    dashboard, assistant, safety = use_case.consumers
    assert dashboard.consumer_gates == (
        RowCountDropGate(name="triage-rows-hold", task="triage-breakdowns", max_drop=0.10),
    )
    # The name defaults to the check.
    assert assistant.consumer_gates[0].name == "row_count_drop"
    assert safety.consumer_gates == ()


def test_consumer_gates_round_trip_through_the_canonical_form():
    use_case = parse_use_case_yaml(USE_CASE)

    again = parse_use_case_yaml(yaml.safe_dump(to_dict(use_case)))

    assert again == canonicalize(use_case)
    dashboard = next(
        c for c in to_dict(use_case)["consumers"] if c["id"] == "reliability-dashboard"
    )
    assert dashboard["consumer_gates"] == [
        {
            "name": "triage-rows-hold",
            "check": "row_count_drop",
            "task": "triage-breakdowns",
            "max_drop": 0.1,
        }
    ]
    safety = next(c for c in to_dict(use_case)["consumers"] if c["id"] == "safety-team")
    assert "consumer_gates" not in safety


@pytest.mark.parametrize(
    ("gates", "message"),
    [
        (
            [{"check": "row_count_drop", "task": "list-machines", "max_drop": 0.1}],
            "reliability-dashboard.consumer_gates[0].task: 'list-machines' is not a Task of",
        ),
        (
            [{"check": "row_count_drop", "max_drop": 0.1}],
            "consumers[0].consumer_gates[0]: missing 'task'",
        ),
        (
            [{"check": "row_count_drop", "task": "triage-breakdowns", "max_drop": 1.5}],
            "reliability-dashboard.consumer_gates[0].max_drop: must be a number between 0 and 1",
        ),
        (
            [{"check": "row_count_drop", "task": "triage-breakdowns", "max_drop": "10%"}],
            "reliability-dashboard.consumer_gates[0].max_drop: must be a number between 0 and 1",
        ),
        (
            [{"check": "row_count_drop", "task": "triage-breakdowns"}],
            "consumers[0].consumer_gates[0]: missing 'max_drop'",
        ),
        (
            [
                {"check": "row_count_drop", "task": "triage-breakdowns", "max_drop": 0.1},
                {"check": "row_count_drop", "task": "triage-breakdowns", "max_drop": 0.2},
            ],
            "reliability-dashboard.consumer_gates[1].name: duplicate Consumer Gate name "
            "'row_count_drop'",
        ),
        (
            [{"check": "fill_rate", "task": "triage-breakdowns"}],
            "consumers[0].consumer_gates[0].check: 'fill_rate' is planned but not built yet",
        ),
        (
            [{"check": "consumer_impact"}],
            "consumers[0].consumer_gates[0].check: 'consumer_impact' is planned but not built yet",
        ),
        (
            [{"check": "row_count_dorp", "task": "triage-breakdowns", "max_drop": 0.1}],
            "consumers[0].consumer_gates[0].check: unknown check 'row_count_dorp'",
        ),
        (
            [
                {
                    "check": "row_count_drop",
                    "task": "triage-breakdowns",
                    "max_drop": 0.1,
                    "min_rows": 3,
                }
            ],
            "consumers[0].consumer_gates[0]: unknown keys ['min_rows']",
        ),
        ("row_count_drop", "consumers[0].consumer_gates: must be a list"),
    ],
)
def test_malformed_consumer_gates_are_rejected_naming_the_field(client, gates, message):
    client.create_knowledge_graph(KG, ontology=ONTOLOGY)

    with pytest.raises(ConsumerGateConfigError) as raised:
        client.register_use_case(KG, use_case_with(**{"reliability-dashboard": gates}))

    assert message in str(raised.value)


def test_a_malformed_consumer_gate_model_is_rejected_in_every_mode(client):
    client.create_knowledge_graph(KG, ontology=ONTOLOGY)
    use_case = parse_use_case_yaml(USE_CASE)
    dashboard = use_case.consumers[0]
    broken = dashboard.__class__(
        **{
            **dashboard.__dict__,
            "consumer_gates": (RowCountDropGate(task="nope", max_drop=0.1),),
        }
    )
    bad = use_case.__class__(**{**use_case.__dict__, "consumers": (broken,)})

    with pytest.raises(ConsumerGateConfigError, match="'nope' is not a Task of"):
        client.register_use_case(KG, bad)


def test_changing_a_consumer_gate_yields_a_new_use_case_version(client):
    client.create_knowledge_graph(KG, ontology=ONTOLOGY)
    first = client.register_use_case(KG, USE_CASE)

    looser = client.register_use_case(
        KG,
        use_case_with(
            **{
                "reliability-dashboard": [
                    {"check": "row_count_drop", "task": "triage-breakdowns", "max_drop": 0.2}
                ]
            }
        ),
    )

    assert looser.number == first.number + 1
    assert looser.use_case.consumers[1].consumer_gates[0].max_drop == 0.2
    assert client.register_use_case(KG, USE_CASE).number == first.number


def test_a_use_case_without_consumer_gates_hashes_as_it_did_before_them(client):
    client.create_knowledge_graph(KG, ontology=ONTOLOGY)
    data = yaml.safe_load(USE_CASE)
    for consumer in data["consumers"]:
        consumer.pop("consumer_gates", None)

    version = client.register_use_case(KG, data)

    # The hash of this Use Case as stored before Consumer Gates existed.
    assert version.content_hash == GATELESS_HASH


GATELESS_HASH = "96422c3fa2235136b4d49d24f095d48b83cb1b8560e32548c6222af53cfcba38"


# --- Evaluating Consumer Gates ----------------------------------------------------------


@pytest.fixture
def plant(client):
    client.create_knowledge_graph(KG, ontology=ONTOLOGY)
    client.bind_graph_source(KG, GraphSourceScope(database="neo4j"))
    client.register_use_case(KG, USE_CASE)
    return KG


def rows(n):
    return [{"n": i} for i in range(n)]


def run_with(client, graph_source, *, technicians=5, downtime=3, machines=4, **kw):
    """A finished Construction Run whose executed questions return the given row counts
    (None: the question's query raises)."""
    for query, count in ((TECHNICIANS, technicians), (DOWNTIME, downtime), (MACHINES, machines)):
        if count is None:
            graph_source._query_results.pop(("neo4j", query), None)
        else:
            graph_source.add_query_result(query, rows(count))
    with client.start_run(KG, **kw) as run:
        pass
    return client.get_run(run.id)


def outcome_of(results, consumer):
    [result] = [r for r in results if r.consumer == consumer]
    [outcome] = result.outcomes
    return result, outcome


def test_a_row_count_drop_past_the_limit_fails_naming_consumer_task_question_and_rows(
    client, plant, graph_source
):
    baseline = run_with(client, graph_source, technicians=5)
    candidate = run_with(client, graph_source, technicians=2)

    results = client.evaluate_consumer_gates(plant)

    result, outcome = outcome_of(results, "reliability-dashboard")
    assert not result.passed and not outcome.passed
    assert outcome.gate.name == "triage-rows-hold"
    assert (result.run_id, result.ontology_version) == (candidate.id, 1)
    assert (result.baseline_run_id, result.baseline_ontology_version) == (baseline.id, 1)
    assert result.use_case_version == 1
    [finding] = outcome.findings
    assert (finding.task, finding.competency_question) == (
        "triage-breakdowns",
        "breakdown-technicians",
    )
    assert (finding.before, finding.after, finding.limit) == (5, 2, 0.10)
    assert finding.change == pytest.approx(-0.6)
    assert finding.missing is None
    assert any("breakdown-technicians" in r and "5 → 2" in r for r in outcome.reasons)


def test_a_drop_within_the_limit_passes(client, plant, graph_source):
    run_with(client, graph_source, technicians=10, machines=4)
    run_with(client, graph_source, technicians=9, machines=2)  # -10%, -50%: both on the limit

    results = client.evaluate_consumer_gates(plant)

    assert all(r.passed for r in results)
    assert all(o.findings == () for r in results for o in r.outcomes)


def test_without_a_baseline_run_every_consumer_gate_fails(client, plant, graph_source):
    run_with(client, graph_source)

    results = client.evaluate_consumer_gates(plant)

    assert [r.passed for r in results] == [False, False]
    assert all(r.baseline_run_id is None for r in results)
    _, outcome = outcome_of(results, "maintenance-assistant")
    assert [f.missing for f in outcome.findings] == ["no_baseline_run"]
    assert "baseline" in outcome.reasons[0].lower()


def _store(tracking_mode, tmp_path):
    """The Store behind `client`, for a state the SDK cannot produce on its own."""
    url = {
        "local": f"sqlite:///{tmp_path / 'stetiq.db'}",
        "remote": f"sqlite:///{tmp_path / 'server.db'}",
    }.get(tracking_mode) or os.environ["STETIQ_TEST_POSTGRES_URL"]
    return SqlStore(url)


def test_a_contract_alias_pointing_to_no_version_is_a_missing_baseline(
    client, plant, graph_source, tracking_mode, tmp_path
):
    run_with(client, graph_source)
    run_with(client, graph_source)
    # E.g. a store edited by hand: the Contract Alias names an Alias that does not exist.
    _store(tracking_mode, tmp_path).set_contract_alias(KG, "gone")

    results = client.evaluate_consumer_gates(plant)

    assert [r.passed for r in results] == [False, False]
    assert all((r.baseline_run_id, r.baseline_ontology_version) == (None, None) for r in results)
    _, outcome = outcome_of(results, "reliability-dashboard")
    assert {f.missing for f in outcome.findings} == {"no_baseline_run"}
    assert "Contract Alias" in outcome.reasons[0]
    assert client.list_consumer_gate_results(plant) == results


def test_the_baseline_is_a_run_on_the_contract_aliass_version(client, plant, graph_source):
    on_v1 = run_with(client, graph_source, technicians=5)
    # A run on another version is never the baseline, however recent.
    v2 = client.register_ontology(
        KG, ONTOLOGY.replace("  - label: WorkOrder", "  - label: WorkOrder\n  - label: Supplier")
    )
    run_with(client, graph_source, technicians=1, ontology_version=v2.number)
    candidate = run_with(client, graph_source, technicians=5, ontology_version=v2.number)

    results = client.evaluate_consumer_gates(plant, run=candidate.id)

    result, _ = outcome_of(results, "reliability-dashboard")
    assert (result.baseline_run_id, result.baseline_ontology_version) == (on_v1.id, 1)
    assert result.ontology_version == v2.number
    assert result.passed


@pytest.mark.parametrize(
    ("before", "after", "missing"),
    [
        ({"technicians": None}, {}, "baseline_error"),
        ({}, {"technicians": None}, "candidate_error"),
    ],
)
def test_an_errored_question_on_either_side_fails(
    client, plant, graph_source, before, after, missing
):
    run_with(client, graph_source, **before)
    run_with(client, graph_source, **after)

    results = client.evaluate_consumer_gates(plant)

    _, outcome = outcome_of(results, "reliability-dashboard")
    assert not outcome.passed
    assert [(f.competency_question, f.missing) for f in outcome.findings] == [
        ("breakdown-technicians", missing)
    ]


def test_a_question_without_a_query_has_no_row_count_and_fails(client, plant, graph_source):
    client.register_use_case(
        KG,
        USE_CASE.replace(
            "competency_questions: [machines]\n    consumer_gates",
            "competency_questions: [machines, spare-parts]\n    consumer_gates",
        ),
    )
    run_with(client, graph_source)
    run_with(client, graph_source)

    results = client.evaluate_consumer_gates(plant, consumer="maintenance-assistant")

    [result] = results
    assert result.use_case_version == 2
    assert [(f.competency_question, f.missing) for f in result.outcomes[0].findings] == [
        ("spare-parts", "baseline_missing")
    ]


def with_question_in_the_assistants_task(question):
    """USE_CASE with `question` (a new, executed question) added to the assistant's Task."""
    data = yaml.safe_load(USE_CASE)
    data["competency_questions"].append(
        {"id": question, "question": "Which suppliers fail?", "query": DOWNTIME}
    )
    [assistant] = [c for c in data["consumers"] if c["id"] == "maintenance-assistant"]
    assistant["tasks"][0]["competency_questions"].append(question)
    return data


def test_a_question_new_since_the_baselines_use_case_version_is_not_compared(
    client, plant, graph_source
):
    baseline = run_with(client, graph_source)  # judged by Use Case Version 1
    client.register_use_case(KG, with_question_in_the_assistants_task("suppliers"))
    run_with(client, graph_source)

    result, outcome = outcome_of(
        client.evaluate_consumer_gates(plant, consumer="maintenance-assistant"),
        "maintenance-assistant",
    )

    assert result.passed and outcome.passed
    assert result.baseline_run_id == baseline.id
    assert outcome.findings == ()
    assert outcome.new_questions == ("suppliers",)
    assert outcome.reasons == (
        "list-machines / suppliers: new, no baseline (not in the baseline run's Use Case "
        "Version 1)",
    )
    assert client.list_consumer_gate_results(plant)[-1].outcomes[0].new_questions == ("suppliers",)


def test_a_new_question_does_not_hide_a_drop_beside_it(client, plant, graph_source):
    run_with(client, graph_source, machines=4)
    client.register_use_case(KG, with_question_in_the_assistants_task("suppliers"))
    run_with(client, graph_source, machines=1)

    _, outcome = outcome_of(
        client.evaluate_consumer_gates(plant, consumer="maintenance-assistant"),
        "maintenance-assistant",
    )

    assert not outcome.passed
    assert [f.competency_question for f in outcome.findings] == ["machines"]
    assert outcome.new_questions == ("suppliers",)


def test_a_new_question_without_a_baseline_run_still_fails(client, plant, graph_source):
    client.register_use_case(KG, with_question_in_the_assistants_task("suppliers"))
    run_with(client, graph_source)

    result, outcome = outcome_of(
        client.evaluate_consumer_gates(plant, consumer="maintenance-assistant"),
        "maintenance-assistant",
    )

    assert not result.passed
    assert {f.missing for f in outcome.findings} == {"no_baseline_run"}


def test_a_baseline_of_zero_rows_cannot_drop(client, plant, graph_source):
    run_with(client, graph_source, technicians=0)
    run_with(client, graph_source, technicians=0)

    _, outcome = outcome_of(client.evaluate_consumer_gates(plant), "reliability-dashboard")

    assert outcome.passed


def test_only_gated_consumers_are_recorded(client, plant, graph_source):
    run_with(client, graph_source)
    run_with(client, graph_source)

    results = client.evaluate_consumer_gates(plant)

    assert sorted(r.consumer for r in results) == ["maintenance-assistant", "reliability-dashboard"]
    assert sorted(r.consumer for r in client.list_consumer_gate_results(plant)) == [
        "maintenance-assistant",
        "reliability-dashboard",
    ]


def test_consumer_restricts_evaluation_to_one_consumer(client, plant, graph_source):
    run_with(client, graph_source)
    run_with(client, graph_source)

    results = client.evaluate_consumer_gates(plant, consumer="maintenance-assistant")

    assert [r.consumer for r in results] == ["maintenance-assistant"]


def test_an_unknown_consumer_is_not_found(client, plant, graph_source):
    run_with(client, graph_source)

    with pytest.raises(NotFoundError):
        client.evaluate_consumer_gates(plant, consumer="nobody")


def test_a_consumer_without_consumer_gates_cannot_be_evaluated_alone(client, plant, graph_source):
    run_with(client, graph_source)

    with pytest.raises(NoConsumerGatesError, match="safety-team"):
        client.evaluate_consumer_gates(plant, consumer="safety-team")


def test_run_and_version_exclude_each_other(client, plant, graph_source):
    run = run_with(client, graph_source)

    with pytest.raises(ConflictingArgumentsError):
        client.evaluate_consumer_gates(plant, run=run.id, version=1)


def test_the_candidate_can_be_named_by_the_version_it_stands_for(client, plant, graph_source):
    first = run_with(client, graph_source, technicians=5)
    run_with(client, graph_source, technicians=1)
    v2 = client.register_ontology(
        KG, ONTOLOGY.replace("  - label: WorkOrder", "  - label: WorkOrder\n  - label: Supplier")
    )
    on_v2 = run_with(client, graph_source, technicians=5, ontology_version=v2.number)

    by_v1 = client.evaluate_consumer_gates(plant, version=1)
    by_v2 = client.evaluate_consumer_gates(plant, version=v2.number)

    # The latest finished run standing for v1 is the second, judged against the first.
    dashboard_v1, _ = outcome_of(by_v1, "reliability-dashboard")
    assert dashboard_v1.baseline_run_id == first.id and not dashboard_v1.passed
    dashboard_v2, _ = outcome_of(by_v2, "reliability-dashboard")
    assert dashboard_v2.run_id == on_v2.id


def test_without_a_finished_run_there_is_nothing_to_judge(client, plant):
    with pytest.raises(NotFoundError, match="finished Construction Run"):
        client.evaluate_consumer_gates(plant)


def test_a_use_case_without_any_consumer_gate_is_refused(client, plant, graph_source):
    data = yaml.safe_load(USE_CASE)
    for consumer in data["consumers"]:
        consumer.pop("consumer_gates", None)
    client.register_use_case(KG, data)
    run_with(client, graph_source)

    with pytest.raises(NoConsumerGatesError, match="declares a Consumer Gate"):
        client.evaluate_consumer_gates(plant)


def test_a_run_of_another_knowledge_graph_is_not_found(client, plant, graph_source):
    client.create_knowledge_graph("other", ontology=ONTOLOGY)
    client.bind_graph_source("other", GraphSourceScope(database="neo4j"))
    with client.start_run("other") as other:
        pass

    with pytest.raises(NotFoundError):
        client.evaluate_consumer_gates(plant, run=other.id)


def test_results_are_listed_oldest_first_and_filtered(client, plant, graph_source):
    run_with(client, graph_source)
    run_with(client, graph_source)
    first = client.evaluate_consumer_gates(plant)
    v2 = client.register_ontology(
        KG, ONTOLOGY.replace("  - label: WorkOrder", "  - label: WorkOrder\n  - label: Supplier")
    )
    run_with(client, graph_source, ontology_version=v2.number)
    second = client.evaluate_consumer_gates(plant, consumer="maintenance-assistant")

    assert client.list_consumer_gate_results(plant) == [*first, *second]
    assert [
        r.ontology_version
        for r in client.list_consumer_gate_results(plant, consumer="maintenance-assistant")
    ] == [1, v2.number]
    assert client.list_consumer_gate_results(plant, version=v2.number) == second


def test_consumer_gate_results_never_reach_the_promotion_audit(client, plant, graph_source):
    run_with(client, graph_source, technicians=5)
    run_with(client, graph_source, technicians=1)
    client.evaluate_consumer_gates(plant)
    v2 = client.register_ontology(
        KG, ONTOLOGY.replace("  - label: WorkOrder", "  - label: WorkOrder\n  - label: Supplier")
    )

    client.set_alias(plant, "production", v2.number)

    assert client.list_promotions(plant)[-1].gate_result is None
    assert client.get_alias(plant, "production").version == v2.number


# --- `stetiq consumer gate` in CI --------------------------------------------------------


@pytest.fixture
def cli_plant(tmp_path, monkeypatch):
    """A local-mode `plant` the CLI reaches through $STETIQ_TRACKING_URI, run from a repo
    whose stetiq.yaml names it; returns the SDK client and the fake Graph Source."""
    uri = f"sqlite:///{tmp_path / 'stetiq.db'}"
    monkeypatch.setenv("STETIQ_TRACKING_URI", uri)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stetiq.yaml").write_text(f"knowledge_graph: {KG}\n")
    graph = InMemoryGraphSource()
    monkeypatch.setattr("stetiq.client.graph_source_from_env", lambda environ=None: graph)
    sdk = stetiq.Client(uri, graph_source=graph)
    sdk.create_knowledge_graph(KG, ontology=ONTOLOGY)
    sdk.bind_graph_source(KG, GraphSourceScope(database="neo4j"))
    sdk.register_use_case(KG, USE_CASE)
    return sdk, graph


def consumer_gate(*args):
    return CliRunner().invoke(app, ["consumer", "gate", *args])


def test_the_cli_exits_3_and_names_the_symptom_when_a_consumer_gate_fails(cli_plant):
    sdk, graph = cli_plant
    run_with(sdk, graph, technicians=5)
    candidate = run_with(sdk, graph, technicians=2)

    result = consumer_gate()  # the Knowledge Graph comes from stetiq.yaml

    assert result.exit_code == CONSUMER_GATE_FAILED_EXIT_CODE == 3, result.output
    lines = result.output.splitlines()
    assert "reliability-dashboard" in lines
    assert "  FAIL  triage-rows-hold" in lines
    assert any(
        "triage-breakdowns / breakdown-technicians: 5 → 2 rows (−60.0%, limit −10%)" in line  # noqa: RUF001 - the minus sign the CLI prints
        for line in lines
    )
    assert "  PASS  row_count_drop" in lines
    assert any("safety-team" in line and "no Consumer Gate" in line for line in lines)
    assert lines[-1].startswith("1 of 2 Consumer Gates failed for plant run " + candidate.id[:8])
    assert [r.passed for r in sdk.list_consumer_gate_results(KG)] == [True, False]


def test_the_cli_exits_0_when_every_consumer_gate_passes(cli_plant):
    sdk, graph = cli_plant
    run_with(sdk, graph)
    run = run_with(sdk, graph)

    result = consumer_gate(KG, "--run", run.id, "--consumer", "reliability-dashboard")

    assert result.exit_code == 0, result.output
    assert "  PASS  triage-rows-hold" in result.output.splitlines()
    assert "maintenance-assistant" not in result.output
    assert result.output.splitlines()[-1].startswith("All 1 Consumer Gates passed")


def test_the_cli_fails_a_missing_baseline_with_exit_3(cli_plant):
    sdk, graph = cli_plant
    run_with(sdk, graph)

    result = consumer_gate()

    assert result.exit_code == 3, result.output
    assert "No baseline" in result.output


def test_the_cli_exits_0_when_only_new_questions_are_not_compared(cli_plant):
    sdk, graph = cli_plant
    run_with(sdk, graph)
    sdk.register_use_case(KG, with_question_in_the_assistants_task("suppliers"))
    run_with(sdk, graph)

    result = consumer_gate("--consumer", "maintenance-assistant")

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "  PASS  row_count_drop" in lines
    assert any("list-machines / suppliers: new, no baseline" in line for line in lines)


@pytest.mark.parametrize(
    "args",
    [
        ("--run", "nope"),
        ("--run", "x", "--version", "1"),
        ("--consumer", "safety-team"),
        ("--config", "missing.yaml"),
    ],
)
def test_the_cli_exits_1_on_an_error(cli_plant, args):
    sdk, graph = cli_plant
    run_with(sdk, graph)

    result = consumer_gate(*args)

    assert result.exit_code == 1, result.output
    assert "error:" in result.output


def test_the_cli_exits_1_without_a_knowledge_graph(cli_plant, tmp_path):
    (tmp_path / "stetiq.yaml").write_text("gates: []\n")

    result = consumer_gate()

    assert result.exit_code == 1
    assert "no Knowledge Graph" in result.output


def test_the_cli_lists_recorded_consumer_gate_results(cli_plant):
    sdk, graph = cli_plant
    run_with(sdk, graph, technicians=5)
    run_with(sdk, graph, technicians=2)
    consumer_gate()

    result = CliRunner().invoke(
        app, ["consumer", "gate-results", KG, "--consumer", "reliability-dashboard"]
    )

    assert result.exit_code == 0, result.output
    assert "FAIL" in result.output and "reliability-dashboard" in result.output
    assert "triage-rows-hold" in result.output
    assert "maintenance-assistant" not in result.output
