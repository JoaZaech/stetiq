"""The platform team's own Evaluator, loaded by the CLI with
`--evaluator transit_evaluators:NamingConventions`.

Custom Evaluators run in the SDK process (here: the `stetiq` command itself), and only
their metrics and details reach the tracking service. The Gate
`names-follow-conventions` in stetiq.yaml reads the recorded result.
"""

from __future__ import annotations

import re

from stetiq import Detail, Evaluation, OntologyVersionEvaluator
from stetiq.evaluation.framework import ratio

PASCAL_CASE = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)*$")
UPPER_SNAKE_CASE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class NamingConventions(OntologyVersionEvaluator):
    """Labels are PascalCase, relationship types UPPER_SNAKE_CASE, property names snake_case.

    A Candidate that an evolving Construction Run proposes spells new Concepts the way
    the Graph Source spells them, so this is where a feed's `wheelchairBoarding` shows up
    before anyone promotes it. Metrics: `violations`, `checked` and `compliance`
    (the share of checked names that follow the convention). One Detail per offender.
    """

    name = "naming_conventions"

    def evaluate(self, version) -> Evaluation:
        ontology = version.ontology
        checked = 0
        offenders: list[Detail] = []

        def check(item: str, pattern: re.Pattern[str], what: str, convention: str) -> None:
            nonlocal checked
            checked += 1
            if not pattern.match(item.rsplit(".", 1)[-1]):
                offenders.append(
                    Detail(
                        item=item,
                        message=f"{what} is not {convention}",
                        metric="violations",
                        data={"kind": what, "convention": convention},
                    )
                )

        for node_type in ontology.node_types:
            check(node_type.label, PASCAL_CASE, "node type label", "PascalCase")
            for prop in node_type.properties:
                check(f"{node_type.label}.{prop.name}", SNAKE_CASE, "property name", "snake_case")
        for rel in ontology.relationship_types:
            check(rel.label, UPPER_SNAKE_CASE, "relationship type", "UPPER_SNAKE_CASE")
            for prop in rel.properties:
                check(f"{rel.label}.{prop.name}", SNAKE_CASE, "property name", "snake_case")
        return Evaluation(
            metrics={
                "violations": len(offenders),
                "checked": checked,
                "compliance": ratio(checked - len(offenders), checked),
            },
            details=offenders,
        )
