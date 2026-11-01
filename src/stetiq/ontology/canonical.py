"""Canonical JSON form of an Ontology and its content hash.

The canonical form is order-independent (Concepts, properties and patterns are
sorted) and omits default values, so two Ontologies with the same structure
always produce byte-identical JSON and therefore the same hash.

A Concept's Definition is stored under the key `description`, the name it had
before Definitions existed, and Alternative Labels and a Deprecation (with its
reason) are omitted when unset, so Ontology Versions registered before any of
them existed keep their hashes.
The stetiq YAML spells the Definition `definition` (`to_dict(definition_key=...)`).
"""

from __future__ import annotations

import json
from typing import Any

from stetiq import digest
from stetiq.ontology.model import (
    Constraint,
    NodeType,
    Ontology,
    Pattern,
    Property,
    RelationshipType,
)

# The canonical key of a Concept's Definition; see the module docstring.
DEFINITION_KEY = "description"


def _documentation(
    c: Property | NodeType | RelationshipType, definition_key: str
) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if c.definition is not None:
        d[definition_key] = c.definition
    if c.alternative_labels:
        d["alternativeLabels"] = list(c.alternative_labels)
    return d


def _deprecation(c: Property | NodeType | RelationshipType) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if c.deprecated:
        d["deprecated"] = True
    if c.replaced_by is not None:
        d["replacedBy"] = c.replaced_by
    if c.deprecation_reason is not None:
        d["deprecationReason"] = c.deprecation_reason
    return d


def _property_to_dict(p: Property, definition_key: str) -> dict[str, Any]:
    d: dict[str, Any] = {"name": p.name, "type": p.type, **_documentation(p, definition_key)}
    if p.required:
        d["required"] = True
    d.update(_deprecation(p))
    return d


def _concept_to_dict(c: NodeType | RelationshipType, definition_key: str) -> dict[str, Any]:
    d: dict[str, Any] = {"label": c.label, **_documentation(c, definition_key)}
    if c.properties:
        d["properties"] = [
            _property_to_dict(p, definition_key) for p in sorted(c.properties, key=lambda p: p.name)
        ]
    d.update(_deprecation(c))
    if isinstance(c, NodeType) and c.parent is not None:
        d["parent"] = c.parent
    return d


def pattern_to_list(p: Pattern) -> list[str]:
    """A Pattern's endpoints in JSON form, `[source, relationship, target]`."""
    return [p.source, p.relationship, p.target]


def _pattern_to_json(p: Pattern) -> list[str] | dict[str, Any]:
    """A Pattern's canonical form: the `[source, relationship, target]` triple, or, when it
    declares a cardinality, the mapping form with a `cardinality` key. Unbounded patterns
    keep the triple, so pre-cardinality hashes are unchanged."""
    cardinality = p.cardinality
    if not cardinality:
        return pattern_to_list(p)
    return {
        "source": p.source,
        "relationship": p.relationship,
        "target": p.target,
        "cardinality": cardinality,
    }


def _pattern_from_json(p: list[str] | dict[str, Any]) -> Pattern:
    if isinstance(p, list):
        source, relationship, target = p
        return Pattern(source, relationship, target)
    bounds = p.get("cardinality", {})
    out, in_ = bounds.get("out", {}), bounds.get("in", {})
    return Pattern(
        p["source"],
        p["relationship"],
        p["target"],
        min_out=out.get("min"),
        max_out=out.get("max"),
        min_in=in_.get("min"),
        max_in=in_.get("max"),
    )


def to_dict(ontology: Ontology, definition_key: str = DEFINITION_KEY) -> dict[str, Any]:
    """The canonical dict form; also the shape of the stetiq YAML, which passes
    `definition_key="definition"`."""
    d: dict[str, Any] = {
        "node_types": [
            _concept_to_dict(n, definition_key)
            for n in sorted(ontology.node_types, key=lambda n: n.label)
        ],
        "relationship_types": [
            _concept_to_dict(r, definition_key)
            for r in sorted(ontology.relationship_types, key=lambda r: r.label)
        ],
        "patterns": [_pattern_to_json(p) for p in sorted(ontology.patterns)],
    }
    if ontology.constraints:  # omitted when empty, so pre-constraint hashes are unchanged
        d["constraints"] = [
            {"type": c.type, "node_type": c.node_type, "property_name": c.property_name}
            for c in sorted(ontology.constraints)
        ]
    return d


def _definition(d: dict[str, Any]) -> str | None:
    return d.get(DEFINITION_KEY, d.get("definition"))


def _property_from_dict(d: dict[str, Any]) -> Property:
    return Property(
        name=d["name"],
        type=d["type"],
        definition=_definition(d),
        required=d.get("required", False),
        alternative_labels=tuple(d.get("alternativeLabels", ())),
        **_deprecation_kwargs(d),
    )


def _deprecation_kwargs(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "deprecated": d.get("deprecated", False),
        "replaced_by": d.get("replacedBy"),
        "deprecation_reason": d.get("deprecationReason"),
    }


def _concept_kwargs(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": d["label"],
        "definition": _definition(d),
        "alternative_labels": tuple(d.get("alternativeLabels", ())),
        "properties": tuple(_property_from_dict(p) for p in d.get("properties", [])),
        **_deprecation_kwargs(d),
    }


def from_dict(d: dict[str, Any]) -> Ontology:
    """Inverse of `to_dict`. Assumes already-validated input."""
    return Ontology(
        node_types=tuple(
            NodeType(**_concept_kwargs(n), parent=n.get("parent")) for n in d.get("node_types", [])
        ),
        relationship_types=tuple(
            RelationshipType(**_concept_kwargs(r)) for r in d.get("relationship_types", [])
        ),
        patterns=tuple(_pattern_from_json(p) for p in d.get("patterns", [])),
        constraints=tuple(Constraint(**c) for c in d.get("constraints", [])),
    )


def canonical_json(ontology: Ontology) -> str:
    return digest.canonical_json(to_dict(ontology))


def from_canonical_json(text: str) -> Ontology:
    return from_dict(json.loads(text))


def content_hash(ontology: Ontology) -> str:
    return digest.content_hash(to_dict(ontology))
