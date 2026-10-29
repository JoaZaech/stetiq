"""The stetiq YAML format, deliberately close to neo4j-graphrag's schema configuration.

    node_types:
      - Customer                      # bare label shorthand
      - label: Ticket
        description: A support request
        properties:
          - {name: opened_at, type: DATE, required: true}
        deprecated: true              # optional
        replacedBy: Case              # optional, a Concept of the same kind
    relationship_types:
      - OPENED
    patterns:
      - [Customer, OPENED, Ticket]    # (source, relationship type, target)
      # or neo4j-graphrag's mapping form: {source: ..., relationship: ..., target: ...}

`parse_yaml` validates and raises `OntologyValidationError` naming the
offending element; `to_yaml` emits the canonical (sorted, defaults omitted) form.
"""

from __future__ import annotations

from typing import Any

import yaml

from stetiq.errors import OntologyValidationError
from stetiq.ontology import canonical
from stetiq.ontology.model import NodeType, Ontology, Pattern, Property, RelationshipType

# neo4j-graphrag's property types.
PROPERTY_TYPES = frozenset(
    {
        "BOOLEAN",
        "DATE",
        "DURATION",
        "FLOAT",
        "INTEGER",
        "LIST",
        "LOCAL_DATETIME",
        "LOCAL_TIME",
        "POINT",
        "STRING",
        "ZONED_DATETIME",
        "ZONED_TIME",
    }
)

_TOP_LEVEL_KEYS = {"node_types", "relationship_types", "patterns"}
_CONCEPT_KEYS = {"label", "description", "properties", "deprecated", "replacedBy"}
_PROPERTY_KEYS = {"name", "type", "description", "required"}


def _fail(element: str, problem: str) -> OntologyValidationError:
    return OntologyValidationError(f"{element}: {problem}")


def _check_keys(element: str, d: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(d) - allowed)
    if unknown:
        raise _fail(element, f"unknown key(s) {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}")


def _optional_str(element: str, value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _fail(element, "must be a string")
    return value


def _bool(element: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise _fail(element, f"must be true or false, got {value!r}")
    return value


def _label(element: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(element, "needs a non-empty string label")
    return value


def _parse_property(element: str, raw: Any) -> Property:
    if not isinstance(raw, dict):
        raise _fail(element, "must be a mapping with name and type")
    if "name" not in raw:
        raise _fail(element, "property needs a name")
    name = _label(element, raw["name"])
    element = f"{element.rsplit('.properties[', 1)[0]}.{name}"
    _check_keys(element, raw, _PROPERTY_KEYS)
    ptype = raw.get("type")
    if ptype not in PROPERTY_TYPES:
        raise _fail(element, f"unknown property type {ptype!r}; allowed: {', '.join(sorted(PROPERTY_TYPES))}")
    return Property(
        name=name,
        type=ptype,
        description=_optional_str(f"{element}.description", raw.get("description")),
        required=_bool(f"{element}.required", raw.get("required", False)),
    )


def _parse_concept(section: str, index: int, raw: Any) -> dict[str, Any]:
    element = f"{section}[{index}]"
    if isinstance(raw, str):
        raw = {"label": raw}
    if not isinstance(raw, dict):
        raise _fail(element, "must be a label or a mapping with a label")
    if "label" not in raw:
        raise _fail(element, "needs a label")
    label = _label(element, raw["label"])
    _check_keys(label, raw, _CONCEPT_KEYS)
    raw_props = raw.get("properties") or []
    if not isinstance(raw_props, list):
        raise _fail(f"{label}.properties", "must be a list")
    properties = tuple(
        _parse_property(f"{label}.properties[{i}]", p) for i, p in enumerate(raw_props)
    )
    seen: set[str] = set()
    for p in properties:
        if p.name in seen:
            raise _fail(f"{label}.{p.name}", "property is declared more than once")
        seen.add(p.name)
    return {
        "label": label,
        "description": _optional_str(f"{label}.description", raw.get("description")),
        "properties": properties,
        "deprecated": _bool(f"{label}.deprecated", raw.get("deprecated", False)),
        "replaced_by": _optional_str(f"{label}.replacedBy", raw.get("replacedBy")),
    }


def _parse_section(doc: dict[str, Any], section: str) -> list[dict[str, Any]]:
    raw = doc.get(section) or []
    if not isinstance(raw, list):
        raise _fail(section, "must be a list")
    concepts = [_parse_concept(section, i, c) for i, c in enumerate(raw)]
    seen: set[str] = set()
    for c in concepts:
        if c["label"] in seen:
            raise _fail(c["label"], f"declared more than once in {section}")
        seen.add(c["label"])
    for c in concepts:
        target = c["replaced_by"]
        if target is not None and (target not in seen or target == c["label"]):
            raise _fail(
                f"{c['label']}.replacedBy",
                f"{target!r} is not another Concept declared in {section}",
            )
    return concepts


def _parse_patterns(doc: dict[str, Any], node_labels: set[str], rel_labels: set[str]) -> list[Pattern]:
    raw = doc.get("patterns") or []
    if not isinstance(raw, list):
        raise _fail("patterns", "must be a list")
    patterns = []
    for i, p in enumerate(raw):
        element = f"patterns[{i}]"
        if isinstance(p, dict) and set(p) == {"source", "relationship", "target"}:
            p = [p["source"], p["relationship"], p["target"]]
        if not (isinstance(p, list) and len(p) == 3 and all(isinstance(x, str) for x in p)):
            raise _fail(element, f"must be a [source, relationship type, target] triple, got {p!r}")
        source, rel, target = p
        for node in (source, target):
            if node not in node_labels:
                raise _fail(f"{element} {p}", f"node type {node!r} is not declared in node_types")
        if rel not in rel_labels:
            raise _fail(f"{element} {p}", f"relationship type {rel!r} is not declared in relationship_types")
        patterns.append(Pattern(source, rel, target))
    return patterns


def parse_yaml(text: str) -> Ontology:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise OntologyValidationError(f"Invalid YAML: {e}") from None
    return parse_dict(doc)


def parse_dict(doc: Any) -> Ontology:
    """Validate a stetiq-format document already parsed from YAML or JSON.

    The canonical dict form (`canonical.to_dict`) is a valid input, which is how
    the server re-validates Ontologies arriving over HTTP.
    """
    if not isinstance(doc, dict):
        raise _fail("top level", "must be a mapping with node_types, relationship_types, patterns")
    _check_keys("top level", doc, _TOP_LEVEL_KEYS)
    nodes = _parse_section(doc, "node_types")
    if not nodes:
        raise _fail("node_types", "a Declared Ontology needs at least one node type")
    rels = _parse_section(doc, "relationship_types")
    patterns = _parse_patterns(doc, {n["label"] for n in nodes}, {r["label"] for r in rels})
    return Ontology(
        node_types=tuple(NodeType(**n) for n in nodes),
        relationship_types=tuple(RelationshipType(**r) for r in rels),
        patterns=tuple(patterns),
    )


def to_yaml(ontology: Ontology) -> str:
    return yaml.safe_dump(canonical.to_dict(ontology), sort_keys=False, allow_unicode=True)
