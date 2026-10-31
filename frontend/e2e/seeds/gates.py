"""Gates: Gate verdicts on the run compare page and the runs charts (Gate Previews)."""

from __future__ import annotations

from typing import Any

import stetiq
from stetiq.graph_source import GraphSourceScope

from ._shared import SUPPORT_V1, add_ada_and_ticket
from .construction_runs import RunReview

# Every check: the parameterised `review` metric Gate covers the `min_confidence=0.5`
# configuration only, so `review (min_confidence=0.8)/score` stays ungated.
GATES = """
gates:
  - name: conformance-floor
    check: conformance
    min_score: 0.6
  - name: review-score
    check: metric
    evaluator: review
    metric: score
    min: 0.8
    parameters: {min_confidence: 0.5}
  - name: no-breaking-changes
    check: ontology_diff
    max_classification: additive
  - name: no-count-drop
    check: count_drop
    max_drop: 0.5
"""


def _graph(*, escalated: bool) -> stetiq.InMemoryGraphSource:
    """Ada and a Ticket; with `escalated`, a Ticket.priority and an `ESCALATED`
    relationship that SUPPORT_V1 lacks (Conformance 0.5455), else none (Conformance 0.75)."""
    graph = stetiq.InMemoryGraphSource()
    ada, ticket = add_ada_and_ticket(graph, priority=2 if escalated else None)
    if escalated:
        graph.add_relationship(ticket, "ESCALATED", ada)
    return graph


def _run(tracking_uri: str, *, escalated: bool, review: float | None, precision: float) -> str:
    client = stetiq.Client(tracking_uri, graph_source=_graph(escalated=escalated))
    with client.start_run("support", ontology_version=1) as run:
        run.log_metrics({"precision": precision})
    if review is not None:
        client.evaluate_run(
            run.id,
            evaluators=(
                RunReview(min_confidence=0.5, score=review),
                RunReview(min_confidence=0.8, score=0.5),
            ),
        )
    return run.id


def gates(client: stetiq.Client) -> dict[str, Any]:
    """`support` (Contract Alias `production` on v1), gated by GATES (`gates`, the YAML),
    with four finished runs, oldest first:

    - `baseline`: escalated graph (Conformance 0.5455 < 0.6, fail), review 0.9 (pass),
      no earlier Observation (count drop passes). The only run with a recorded Gate
      result (overall fail), so its verdicts are *recorded*; the others are previews
      whose definitions come from that result.
    - `regressed`: escalated graph (Conformance fail), review 0.6 (fail).
    - `unreviewed`: plain graph (Conformance 0.75, pass), no `review` result at all (the
      metric Gate fails with no value: "no result"), and `ESCALATED` disappeared since
      the Observation before (count drop fails).
    - `improved`: plain graph (Conformance pass), review 0.95 (pass), every Gate passes.

    Every reviewed run also has `review (min_confidence=0.8)/score` 0.5, which no Gate
    covers, and each logs an ungated `precision` metric. The Ontology Diff Gate passes
    for all (every run declares v1, the Contract Alias's version).
    """
    client.create_knowledge_graph("support", ontology=SUPPORT_V1)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    client.set_alias("support", "production", 1)
    uri = client.tracking_uri
    baseline = _run(uri, escalated=True, review=0.9, precision=0.9)
    client.evaluate_gates("support", GATES, run=baseline)
    regressed = _run(uri, escalated=True, review=0.6, precision=0.8)
    unreviewed = _run(uri, escalated=False, review=None, precision=0.85)
    improved = _run(uri, escalated=False, review=0.95, precision=0.95)
    return {
        "baseline": baseline,
        "regressed": regressed,
        "unreviewed": unreviewed,
        "improved": improved,
        "gates": GATES,
    }


def never_gated(client: stetiq.Client) -> dict[str, Any]:
    """`support` with two reviewed runs and no Gate result ever: `first`, `second`."""
    client.create_knowledge_graph("support", ontology=SUPPORT_V1)
    client.bind_graph_source("support", GraphSourceScope(database="neo4j"))
    uri = client.tracking_uri
    first = _run(uri, escalated=True, review=0.9, precision=0.9)
    second = _run(uri, escalated=False, review=0.6, precision=0.8)
    return {"first": first, "second": second}


SCENARIOS = (gates, never_gated)
