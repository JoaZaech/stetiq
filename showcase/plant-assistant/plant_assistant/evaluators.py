"""The pipeline's own Evaluators, registered on the stetiq Client (copied from plant-kg).

They run in the show's process (the SDK side); only their metrics and details reach the
stetiq server. Both are named in the Gates of stetiq.yaml.
"""

from __future__ import annotations

from stetiq import ConstructionRunEvaluator, Detail, Evaluation, OntologyVersionEvaluator

WORK_ORDER_COUNT = "MATCH (w:WorkOrder) RETURN count(w) AS work_orders"
WORK_ORDERS_WITHOUT_FOLLOW_UPS = """
MATCH (w:WorkOrder) WHERE NOT (w)-[:HAS_FOLLOW_UP]->(:FollowUp)
RETURN count(w) AS work_orders
"""


def _ratio(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


class Documented(OntologyVersionEvaluator):
    """Every node type and relationship type should say what it means.

    Metrics: `undocumented` (how many have no Definition) and `documented_ratio`.
    One Detail per undocumented Concept.
    """

    name = "documented"

    def evaluate(self, version) -> Evaluation:
        concepts = [*version.ontology.node_types, *version.ontology.relationship_types]
        missing = [c.label for c in concepts if not c.definition]
        return Evaluation(
            metrics={
                "undocumented": len(missing),
                "documented_ratio": _ratio(len(concepts) - len(missing), len(concepts)),
            },
            details=[Detail(item=label, message="has no Definition") for label in missing],
        )


class ReportCoverage(ConstructionRunEvaluator):
    """Did every work order get its technician's report extracted?

    A work order comes from the CMMS export; its follow-ups only exist in the
    technician's free-text report, so a work order without follow-ups means the
    pipeline could not read its report. Counts only (ADR 0001).
    """

    name = "report_coverage"

    def evaluate(self, run) -> Evaluation:
        [total] = run.graph_source.execute_read(WORK_ORDER_COUNT)
        [missing] = run.graph_source.execute_read(WORK_ORDERS_WITHOUT_FOLLOW_UPS)
        work_orders, without = total["work_orders"], missing["work_orders"]
        return Evaluation(
            metrics={
                "work_orders": work_orders,
                "without_follow_ups": without,
                "coverage": _ratio(work_orders - without, work_orders),
            }
        )
