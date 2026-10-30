"""Built-in reference-free structural Evaluators for Ontology Versions.

They run automatically, inside the tracking service, whenever a new Ontology
Version is created, so every version has a structural quality record.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from stetiq.evaluation.framework import Detail, Evaluation, OntologyVersionEvaluator, ratio
from stetiq.ontology.model import NodeType, Ontology, Property, RelationshipType

if TYPE_CHECKING:
    from stetiq.tracking.entities import OntologyVersion


def _levels(ontology: Ontology) -> dict[str, int]:
    """Hierarchy level per node type: roots are level 1 (validation rules out cycles)."""
    parents = {n.label: n.parent for n in ontology.node_types}
    levels: dict[str, int] = {}

    def level(label: str) -> int:
        if label not in levels:
            parent = parents[label]
            levels[label] = 1 if parent is None else level(parent) + 1
        return levels[label]

    for label in parents:
        level(label)
    return levels


def _ancestors_or_self(ontology: Ontology, label: str) -> list[str]:
    chain = [label]
    while (parent := ontology.node_type(chain[-1]).parent) is not None:
        chain.append(parent)
    return chain


class Hierarchy(OntologyVersionEvaluator):
    """Depth and breadth of the node-type hierarchy (a flat Ontology has depth 1)."""

    name = "hierarchy"

    def evaluate(self, version: OntologyVersion) -> Evaluation:
        o = version.ontology
        levels = _levels(o)
        per_level = Counter(levels.values())
        children = Counter(n.parent for n in o.node_types if n.parent is not None)
        return Evaluation(
            metrics={
                "max_depth": max(levels.values()),
                "max_breadth": max(per_level.values()),
                "root_node_types": per_level[1],
                "max_children": max(children.values(), default=0),
            }
        )


class IsolatedNodeTypes(OntologyVersionEvaluator):
    """Node types connected to no pattern, directly, through an ancestor or through a descendant."""

    name = "isolated_node_types"

    def evaluate(self, version: OntologyVersion) -> Evaluation:
        o = version.ontology
        in_pattern = {p.source for p in o.patterns} | {p.target for p in o.patterns}
        # Any node type on the ancestor chain of a pattern participant is connected to it.
        connected = {a for label in in_pattern for a in _ancestors_or_self(o, label)}
        isolated = sorted(
            n.label
            for n in o.node_types
            if not connected.intersection(_ancestors_or_self(o, n.label))
        )
        return Evaluation(
            metrics={
                "isolated_node_types": len(isolated),
                "isolated_node_type_ratio": ratio(len(isolated), len(o.node_types)),
            },
            details=tuple(
                Detail(label, "is connected to no pattern", "isolated_node_types")
                for label in isolated
            ),
        )


class OrphanConcepts(OntologyVersionEvaluator):
    """Concepts nothing else in the Ontology refers to.

    A relationship type used by no pattern; a node type in no pattern with
    neither a parent nor children.
    """

    name = "orphan_concepts"

    def evaluate(self, version: OntologyVersion) -> Evaluation:
        o = version.ontology
        in_pattern = {p.source for p in o.patterns} | {p.target for p in o.patterns}
        in_hierarchy = {n.parent for n in o.node_types if n.parent is not None} | {
            n.label for n in o.node_types if n.parent is not None
        }
        used_relationships = {p.relationship for p in o.patterns}
        nodes = sorted(
            n.label for n in o.node_types if n.label not in in_pattern | in_hierarchy
        )
        relationships = sorted(
            r.label for r in o.relationship_types if r.label not in used_relationships
        )
        total = len(o.node_types) + len(o.relationship_types)
        return Evaluation(
            metrics={
                "orphan_concepts": len(nodes) + len(relationships),
                "orphan_node_types": len(nodes),
                "orphan_relationship_types": len(relationships),
                "orphan_concept_ratio": ratio(len(nodes) + len(relationships), total),
            },
            details=(
                *(Detail(n, "in no pattern and no hierarchy", "orphan_node_types") for n in nodes),
                *(
                    Detail(r, "used by no pattern", "orphan_relationship_types")
                    for r in relationships
                ),
            ),
        )


def _signature(properties: tuple[Property, ...]) -> frozenset[tuple[str, str]]:
    return frozenset((p.name, p.type) for p in properties)


def _redundant_patterns(o: Ontology, lineage: dict[str, list[str]]) -> list[Detail]:
    details = []
    for p in sorted(o.patterns):
        general = next(
            (
                q
                for q in o.patterns
                if q != p
                and q.relationship == p.relationship
                and q.source in lineage[p.source]
                and q.target in lineage[p.target]
            ),
            None,
        )
        if general is not None:
            details.append(
                Detail(str(p), f"implied by {general}", "redundant_patterns")
            )
    return details


def _redundant_properties(o: Ontology, lineage: dict[str, list[str]]) -> list[Detail]:
    details = []
    for n in sorted(o.node_types, key=lambda n: n.label):
        for prop in sorted(n.properties, key=lambda p: p.name):
            owner = next(
                (
                    a
                    for a in lineage[n.label][1:]
                    if (prop.name, prop.type) in _signature(o.node_type(a).properties)
                ),
                None,
            )
            if owner is not None:
                details.append(
                    Detail(
                        f"{n.label}.{prop.name}",
                        f"restates {owner}.{prop.name}",
                        "redundant_properties",
                    )
                )
    return details


def _duplicate_structure(
    concepts: tuple[NodeType, ...] | tuple[RelationshipType, ...], lineage: dict[str, list[str]]
) -> list[Detail]:
    def related(a: str, b: str) -> bool:
        return a in lineage.get(b, [b]) or b in lineage.get(a, [a])

    details = []
    for c in sorted(concepts, key=lambda c: c.label):
        sig = _signature(c.properties)
        twins = sorted(
            d.label
            for d in concepts
            if sig
            and d.label != c.label
            and _signature(d.properties) == sig
            and not related(c.label, d.label)
        )
        if twins:
            details.append(
                Detail(c.label, f"same properties as {', '.join(twins)}", "duplicate_structure_concepts")
            )
    return details


class Redundancy(OntologyVersionEvaluator):
    """Structure stated more than once.

    - redundant pattern: implied by another pattern with the same relationship
      type whose endpoints are ancestors-or-self of its endpoints
    - redundant property: restates (same name and type) a property of an ancestor
    - duplicate-structure Concept: same non-empty property signature as another
      Concept of the same kind that is not its ancestor or descendant
    """

    name = "redundancy"
    _METRICS = ("redundant_patterns", "redundant_properties", "duplicate_structure_concepts")

    def evaluate(self, version: OntologyVersion) -> Evaluation:
        o = version.ontology
        lineage = {n.label: _ancestors_or_self(o, n.label) for n in o.node_types}
        details = [
            *_redundant_patterns(o, lineage),
            *_redundant_properties(o, lineage),
            *_duplicate_structure(o.node_types, lineage),
            *_duplicate_structure(o.relationship_types, {}),
        ]
        counts = Counter(d.metric for d in details)
        return Evaluation(
            metrics={m: counts[m] for m in self._METRICS}, details=tuple(details)
        )


class ConstraintConsistency(OntologyVersionEvaluator):
    """Constraints and deprecations that validation allows but that contradict each other.

    - inherited duplicate constraint: already holds through an ancestor's constraint
    - unique optional property: uniqueness on a property that is not required
    - constraint on deprecated: constrains a deprecated node type
    - deprecated replacement: `replacedBy` points to a Concept that is itself deprecated
    """

    name = "constraint_consistency"
    _METRICS = (
        "inherited_duplicate_constraints",
        "unique_optional_properties",
        "constraints_on_deprecated",
        "deprecated_replacements",
    )

    def evaluate(self, version: OntologyVersion) -> Evaluation:
        o = version.ontology
        unique = {(c.node_type, c.property_name) for c in o.constraints if c.type == "UNIQUENESS"}
        details: list[Detail] = []
        for c in sorted(o.constraints):
            item = f"{c.node_type}.{c.property_name}"
            lineage = _ancestors_or_self(o, c.node_type)
            via = next((a for a in lineage[1:] if (a, c.property_name) in unique), None)
            if via is not None:
                details.append(
                    Detail(item, f"already unique via {via}", "inherited_duplicate_constraints")
                )
            prop = next(
                p for a in lineage for p in o.node_type(a).properties if p.name == c.property_name
            )
            if c.type == "UNIQUENESS" and not prop.required:
                details.append(
                    Detail(item, "unique but not required", "unique_optional_properties")
                )
            if o.node_type(c.node_type).deprecated:
                details.append(
                    Detail(item, f"{c.node_type} is deprecated", "constraints_on_deprecated")
                )
        for concepts, lookup in (
            (o.node_types, o.node_type),
            (o.relationship_types, o.relationship_type),
        ):
            for concept in sorted(concepts, key=lambda c: c.label):
                if concept.replaced_by is not None and lookup(concept.replaced_by).deprecated:
                    details.append(
                        Detail(
                            concept.label,
                            f"replacedBy {concept.replaced_by}, which is deprecated",
                            "deprecated_replacements",
                        )
                    )
        counts = Counter(d.metric for d in details)
        return Evaluation(
            metrics={"inconsistencies": len(details), **{m: counts[m] for m in self._METRICS}},
            details=tuple(details),
        )


BUILT_IN_EVALUATORS: tuple[OntologyVersionEvaluator, ...] = (
    ConstraintConsistency(),
    Hierarchy(),
    IsolatedNodeTypes(),
    OrphanConcepts(),
    Redundancy(),
)
