"""Concept references: what a Competency Question needs from an Ontology.

A requirement is one of
- `ConceptRef(label)`: a node or relationship type (either kind satisfies it),
- `NodeTypeRef(label)` / `RelationshipTypeRef(labels)`: a typed reference read from a
  query (`labels` are alternatives, e.g. `[:OPENED|FILED]`),
- `PropertyRef(owners, name)`: an attribute of one of `owners`,
- `PathRef(source, relationships, target, directed)`: a pattern; `None` / `()` leave
  an end or the relationship open.

`str(ref)` is its Concept identity as used in results: `Ticket`, `Ticket.opened_at`,
`(Customer)-[OPENED]->(Ticket)`. `parse_concept_reference` reads that same syntax
(explicit Concept mappings, and mappings returned by a model).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENT = r"[^\s()\[\]{}.:|`,-][^\s()\[\]{}.:|`,]*"
_LABEL_RE = re.compile(rf"^({_IDENT})$")
_PROPERTY_RE = re.compile(rf"^({_IDENT})\.({_IDENT})$")
_PATH_RE = re.compile(rf"^\(({_IDENT})?\)(<)?-\[({_IDENT}(?:\|{_IDENT})*)?\]-(>)?\(({_IDENT})?\)$")


@dataclass(frozen=True)
class ConceptRef:
    label: str

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True)
class NodeTypeRef:
    label: str

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True)
class RelationshipTypeRef:
    labels: tuple[str, ...]

    def __str__(self) -> str:
        return "|".join(self.labels)


@dataclass(frozen=True)
class PropertyRef:
    owners: tuple[str, ...]
    name: str

    def __str__(self) -> str:
        return f"{'|'.join(self.owners)}.{self.name}"


@dataclass(frozen=True)
class PathRef:
    source: str | None
    relationships: tuple[str, ...]
    target: str | None
    directed: bool = True

    def __str__(self) -> str:
        rel = "|".join(self.relationships)
        arrow = "->" if self.directed else "-"
        return f"({self.source or ''})-[{rel}]{arrow}({self.target or ''})"


Requirement = ConceptRef | NodeTypeRef | RelationshipTypeRef | PropertyRef | PathRef


def parse_concept_reference(text: str) -> Requirement:
    """Parse `Label`, `Owner.property` or `(Source)-[REL]->(Target)`; ValueError if malformed."""
    text = text.strip()
    if m := _LABEL_RE.match(text):
        return ConceptRef(m.group(1))
    if m := _PROPERTY_RE.match(text):
        return PropertyRef((m.group(1),), m.group(2))
    if m := _PATH_RE.match(text):
        source, backwards, rels, forwards, target = m.groups()
        if backwards and forwards:
            raise ValueError(f"{text!r}: a path has one direction")
        if backwards:
            source, target = target, source
        return PathRef(
            source=source,
            relationships=tuple(rels.split("|")) if rels else (),
            target=target,
            directed=bool(backwards or forwards),
        )
    raise ValueError(
        f"{text!r} is not a Concept reference "
        "(expected Label, Owner.property or (Source)-[REL]->(Target))"
    )
