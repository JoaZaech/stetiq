"""Gold-ontology alignment: compare an Ontology Version with a reference ("gold") one.

Concepts are matched by identity (their name), the same identity the Ontology
Diff uses across versions: node types and relationship types by label, attributes
as `Owner.property`. A node type and a relationship type never match each other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stetiq.evaluation.framework import Detail, Evaluation, OntologyVersionEvaluator, ratio
from stetiq.ontology.model import Ontology

if TYPE_CHECKING:
    from stetiq.tracking.entities import OntologyVersion


def _concepts(ontology: Ontology) -> dict[tuple[str, str], str]:
    """(kind, identity) -> the Concept's display name."""
    concepts: dict[tuple[str, str], str] = {}
    for kind, types in (("node", ontology.node_types), ("relationship", ontology.relationship_types)):
        for t in types:
            concepts[(kind, t.label)] = t.label
            for p in t.properties:
                name = f"{t.label}.{p.name}"
                concepts[(kind, name)] = name
    return concepts


class GoldOntologyAlignment(OntologyVersionEvaluator):
    """Precision and recall of an Ontology Version's Concepts against a gold Ontology Version.

    The reference is chosen per evaluation: construct one per gold version and pass
    it to `Client.evaluate(kg, n, evaluators=[GoldOntologyAlignment(gold)])`. The
    result records which reference was used in its `parameters`.
    """

    name = "gold_alignment"

    def __init__(self, reference: OntologyVersion) -> None:
        self.reference = reference

    @property
    def parameters(self) -> dict[str, str | int]:
        return {
            "reference_knowledge_graph": self.reference.knowledge_graph,
            "reference_version": self.reference.number,
        }

    def evaluate(self, version: OntologyVersion) -> Evaluation:
        evaluated = _concepts(version.ontology)
        reference = _concepts(self.reference.ontology)
        matched = sorted(evaluated.keys() & reference.keys())
        extra = sorted(evaluated.keys() - reference.keys())
        missing = sorted(reference.keys() - evaluated.keys())
        precision = ratio(len(matched), len(evaluated))
        recall = ratio(len(matched), len(reference))
        f1 = ratio(2 * precision * recall, precision + recall)
        return Evaluation(
            metrics={
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "matched_concepts": len(matched),
                "unmatched_evaluated_concepts": len(extra),
                "unmatched_reference_concepts": len(missing),
            },
            details=(
                *(Detail(evaluated[k], "in the reference", "matched_concepts") for k in matched),
                *(
                    Detail(evaluated[k], "not in the reference", "unmatched_evaluated_concepts")
                    for k in extra
                ),
                *(
                    Detail(reference[k], "missing from the evaluated version", "unmatched_reference_concepts")
                    for k in missing
                ),
            ),
        )
