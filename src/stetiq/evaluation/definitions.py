"""The `definitions` Evaluator: which Concepts and Vocabulary Values lack a Definition.

A built-in that runs inside the tracking service on every new Ontology Version, like the
structural Evaluators. Deprecated Concepts and Vocabulary Values are not counted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stetiq.evaluation.framework import Detail, Evaluation, OntologyVersionEvaluator
from stetiq.ontology.model import is_deprecated, live_concepts

if TYPE_CHECKING:
    from stetiq.tracking.entities import OntologyVersion

DEFINITIONS_EVALUATOR = "definitions"

_CONCEPTS = "concepts_without_definition"
_VALUES = "vocabulary_values_without_definition"


def _documented(definition: str | None) -> bool:
    return bool(definition and definition.strip())


class Definitions(OntologyVersionEvaluator):
    """Concepts and Vocabulary Values without a Definition (a blank one counts as none).

    Metrics: `concepts_without_definition`, `vocabulary_values_without_definition` and
    `definition_ratio`, the share of counted Concepts and Values that have one (1.0 when
    there is nothing to count). One Detail per item without a Definition: `item` is
    `Label`, `Owner.attribute` or `Vocabulary.value`, `metric` the count it falls in, and
    `data` is `{kind}` (`node_type`, `relationship_type`, `property` or `vocabulary_value`).
    Deprecated items, and the attributes of a deprecated class or relation, are skipped.
    """

    name = DEFINITIONS_EVALUATOR

    def evaluate(self, version: OntologyVersion) -> Evaluation:
        ontology = version.ontology
        items = [
            (kind, identity, concept.definition, _CONCEPTS)
            for kind, identity, concept in live_concepts(ontology)
        ]
        items.extend(
            ("vocabulary_value", f"{vocabulary.label}.{value.label}", value.definition, _VALUES)
            for vocabulary in ontology.vocabularies
            for value in vocabulary.values
            if not is_deprecated(value)
        )
        details = [
            Detail(item=identity, message="no Definition", metric=metric, data={"kind": kind})
            for kind, identity, definition, metric in items
            if not _documented(definition)
        ]
        total = len(items)
        return Evaluation(
            metrics={
                _CONCEPTS: sum(d.metric == _CONCEPTS for d in details),
                _VALUES: sum(d.metric == _VALUES for d in details),
                "definition_ratio": (total - len(details)) / total if total else 1.0,
            },
            details=details,
        )
