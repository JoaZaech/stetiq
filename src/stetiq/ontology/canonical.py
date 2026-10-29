"""Canonical JSON form of an Ontology and its content hash.

The canonical form is order-independent (Concepts, properties and patterns are
sorted) and omits default values, so two Ontologies with the same structure
always produce byte-identical JSON and therefore the same hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from stetiq.ontology.model import (
    Constraint,
    NodeType,
    Ontology,
    Pattern,
    Property,
    RelationshipType,
)


def _property_to_dict(p: Property) -> dict[str, Any]:
    d: dict[str, Any] = {"name": p.name, "type": p.type}
    if p.description is not None:
        d["description"] = p.description
    if p.required:
        d["required"] = True
    return d


def _concept_to_dict(c: NodeType | RelationshipType) -> dict[str, Any]:
    d: dict[str, Any] = {"label": c.label}
    if c.description is not None:
        d["description"] = c.description
    if c.properties:
        d["properties"] = [
            _property_to_dict(p) for p in sorted(c.properties, key=lambda p: p.name)
        ]
    if c.deprecated:
        d["deprecated"] = True
    if c.replaced_by is not None:
        d["replacedBy"] = c.replaced_by
    if isinstance(c, NodeType) and c.parent is not None:
        d["parent"] = c.parent
    return d


def to_dict(ontology: Ontology) -> dict[str, Any]:
    """The canonical dict form; also the shape of the stetiq YAML."""
    d: dict[str, Any] = {
        "node_types": [
            _concept_to_dict(n) for n in sorted(ontology.node_types, key=lambda n: n.label)
        ],
        "relationship_types": [
            _concept_to_dict(r)
            for r in sorted(ontology.relationship_types, key=lambda r: r.label)
        ],
        "patterns": [[p.source, p.relationship, p.target] for p in sorted(ontology.patterns)],
    }
    if ontology.constraints:  # omitted when empty, so pre-constraint hashes are unchanged
        d["constraints"] = [
            {"type": c.type, "node_type": c.node_type, "property_name": c.property_name}
            for c in sorted(ontology.constraints)
        ]
    return d


def _property_from_dict(d: dict[str, Any]) -> Property:
    return Property(
        name=d["name"],
        type=d["type"],
        description=d.get("description"),
        required=d.get("required", False),
    )


def _concept_kwargs(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": d["label"],
        "description": d.get("description"),
        "properties": tuple(_property_from_dict(p) for p in d.get("properties", [])),
        "deprecated": d.get("deprecated", False),
        "replaced_by": d.get("replacedBy"),
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
        patterns=tuple(Pattern(*p) for p in d.get("patterns", [])),
        constraints=tuple(Constraint(**c) for c in d.get("constraints", [])),
    )


def canonical_json(ontology: Ontology) -> str:
    return json.dumps(to_dict(ontology), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def from_canonical_json(text: str) -> Ontology:
    return from_dict(json.loads(text))


def content_hash(ontology: Ontology) -> str:
    return hashlib.sha256(canonical_json(ontology).encode("utf-8")).hexdigest()
