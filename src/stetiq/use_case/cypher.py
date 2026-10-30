"""Read the Concepts and paths a Cypher query relies on.

This is a lightweight pattern reader, not a Cypher parser: it finds node patterns
`(v:Label {key: ...})`, the relationship connectors between consecutive node
patterns `-[r:TYPE|OTHER *1..2 {key: ...}]->`, and property accesses `v.prop`
on variables bound in those patterns. That covers MATCH / OPTIONAL MATCH / WHERE
pattern predicates, which is what structural answerability needs. String literals
and comments are ignored.
"""

from __future__ import annotations

import itertools
import re

from stetiq.use_case.concepts import (
    NodeTypeRef,
    PathRef,
    PropertyRef,
    RelationshipTypeRef,
    Requirement,
)

_ID = r"(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)"
_STRINGS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_NODE = re.compile(
    rf"\(\s*(?P<var>{_ID})?\s*(?P<labels>:\s*{_ID}(?:\s*[:&|]\s*{_ID})*)?\s*"
    rf"(?P<props>\{{[^{{}}]*\}})?\s*\)"
)
_CONNECTOR = re.compile(r"\s*(?P<back><)?\s*-\s*(?:\[(?P<body>[^\]]*)\])?\s*-\s*(?P<fwd>>)?\s*$")
_REL_BODY = re.compile(
    rf"^\s*(?P<var>{_ID})?\s*(?::\s*(?P<types>{_ID}(?:\s*\|\s*:?\s*{_ID})*))?\s*"
    rf"(?P<length>\*[^{{]*)?\s*(?P<props>\{{.*\}})?\s*$",
    re.S,
)
_MAP_KEY = re.compile(rf"(?:^|[{{,])\s*({_ID})\s*:")
_PROPERTY_ACCESS = re.compile(rf"(?<![\w$.`])({_ID})\s*\.\s*({_ID})")
_LABEL = re.compile(_ID)


def _name(identifier: str) -> str:
    return identifier[1:-1] if identifier.startswith("`") else identifier


def _labels(text: str | None) -> tuple[str, ...]:
    return tuple(_name(m) for m in _LABEL.findall(text or ""))


def _map_keys(text: str | None) -> list[str]:
    return [_name(k) for k in _MAP_KEY.findall(text or "")]


def requirements_from_query(query: str) -> list[Requirement]:
    """The node types, relationship types, attributes and paths `query` uses, in order."""
    text = _COMMENTS.sub(" ", _STRINGS.sub("''", query))
    nodes = [m for m in _NODE.finditer(text) if not (m.start() and text[m.start() - 1].isalnum())]

    # links[i]: how nodes[i] connects to nodes[i-1], as (connector, relationship body),
    # or None when they are not one chain (e.g. separate clauses or a function call).
    links: list[tuple[re.Match, re.Match] | None] = [None]
    for prev, node in itertools.pairwise(nodes):
        connector = _CONNECTOR.match(text, prev.end(), node.start())
        body = _REL_BODY.match(connector.group("body") or "") if connector else None
        links.append((connector, body) if connector and body else None)

    # Variables -> the labels / relationship types they are bound to, anywhere in the query.
    node_vars: dict[str, tuple[str, ...]] = {}
    rel_vars: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        if node.group("var") and node.group("labels"):
            node_vars.setdefault(_name(node.group("var")), _labels(node.group("labels")))
    for link in links:
        if link and link[1].group("var") and link[1].group("types"):
            rel_vars.setdefault(_name(link[1].group("var")), _labels(link[1].group("types")))

    def node_labels(node: re.Match) -> tuple[str, ...]:
        if node.group("labels"):
            return _labels(node.group("labels"))
        return node_vars.get(_name(node.group("var")), ()) if node.group("var") else ()

    found: list[Requirement] = []

    def need(req: Requirement) -> None:
        if req not in found:
            found.append(req)

    for i, node in enumerate(nodes):
        labels = node_labels(node)
        link = links[i]
        types: tuple[str, ...] = ()
        if link:
            body = link[1]
            types = _labels(body.group("types"))
            if body.group("var") and not types:
                types = rel_vars.get(_name(body.group("var")), ())
            if types:
                need(RelationshipTypeRef(types))
                for key in _map_keys(body.group("props")):
                    need(PropertyRef(types, key))
        for label in _labels(node.group("labels")):
            need(NodeTypeRef(label))
        if labels:
            for key in _map_keys(node.group("props")):
                need(PropertyRef(labels, key))
        if link and not link[1].group("length"):  # variable length: any intermediate path
            connector = link[0]
            source, target = node_labels(nodes[i - 1]), labels
            backwards = bool(connector.group("back")) and not connector.group("fwd")
            if backwards:
                source, target = target, source
            if source or target or types:
                need(
                    PathRef(
                        source=source[0] if source else None,
                        relationships=types,
                        target=target[0] if target else None,
                        directed=bool(connector.group("back")) != bool(connector.group("fwd")),
                    )
                )

    for var, prop in _PROPERTY_ACCESS.findall(text):
        var, prop = _name(var), _name(prop)
        if var in node_vars:
            need(PropertyRef(node_vars[var], prop))
        elif var in rel_vars:
            need(PropertyRef(rel_vars[var], prop))
    return found
