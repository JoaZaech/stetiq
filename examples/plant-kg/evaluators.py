"""The plant's own Evaluators, registered on the stetiq Client.

They run in this process (the SDK side); only their metrics and details reach the
tracking service. Both are named in the Gates of stetiq.yaml.
"""

from __future__ import annotations

from graphdb import WORK_ORDER_COUNT, WORK_ORDERS_WITHOUT_FOLLOW_UPS

from stetiq import ConstructionRunEvaluator, Detail, Evaluation, OntologyVersionEvaluator
from stetiq.evaluation.framework import ratio


class Documented(OntologyVersionEvaluator):
    """Every node type and relationship type should say what it means.

    Metrics: `undocumented` (how many have no description) and `documented_ratio`.
    One Detail per undocumented Concept.
    """

    name = "documented"

    def evaluate(self, version) -> Evaluation:
        concepts = [*version.ontology.node_types, *version.ontology.relationship_types]
        missing = [c.label for c in concepts if not c.description]
        return Evaluation(
            metrics={
                "undocumented": len(missing),
                "documented_ratio": ratio(len(concepts) - len(missing), len(concepts)),
            },
            details=[Detail(item=label, message="has no description") for label in missing],
        )


class ReportCoverage(ConstructionRunEvaluator):
    """Did every work order get its technician's report extracted?

    A work order comes from the CMMS export; its follow-ups only exist in the
    technician's free-text report. A work order without follow-ups means the
    pipeline could not read its report. Counts only (ADR 0001): the rows are
    aggregates and nothing names an individual work order.
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
                "coverage": ratio(work_orders - without, work_orders),
            }
        )
