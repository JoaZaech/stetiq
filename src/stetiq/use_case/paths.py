"""Which of an Ontology's patterns can serve a Competency Question's path, hierarchy-aware."""

from __future__ import annotations

from stetiq.ontology.model import Ontology, Pattern
from stetiq.use_case.concepts import PathRef


class PathIndex:
    """An Ontology's node-type hierarchy and patterns, for matching paths against.

    A node type, its ancestors and its descendants can all stand in for each other (a
    pattern on `Party` serves a path about `Customer`, and vice versa).
    """

    def __init__(self, ontology: Ontology) -> None:
        self.ontology = ontology
        self._parent = {n.label: n.parent for n in ontology.node_types}
        self._children: dict[str, list[str]] = {}
        for n in ontology.node_types:
            if n.parent:
                self._children.setdefault(n.parent, []).append(n.label)

    def related(self, label: str) -> set[str]:
        """The node type, its ancestors and its descendants."""
        out = {label}
        parent = self._parent.get(label)
        while parent and parent not in out:
            out.add(parent)
            parent = self._parent.get(parent)
        stack = list(self._children.get(label, ()))
        while stack:
            child = stack.pop()
            if child not in out:
                out.add(child)
                stack.extend(self._children.get(child, ()))
        return out

    def serves(self, pattern: Pattern, path: PathRef) -> bool:
        """Whether `pattern` can serve `path`: one of its relationships (any, when it names
        none) between related node types, either way round unless the path is directed."""
        if path.relationships and pattern.relationship not in path.relationships:
            return False
        sources = self.related(path.source) if path.source else None
        targets = self.related(path.target) if path.target else None

        def fits(s: str, t: str) -> bool:
            return (sources is None or s in sources) and (targets is None or t in targets)

        return fits(pattern.source, pattern.target) or (
            not path.directed and fits(pattern.target, pattern.source)
        )

    def has_path(self, path: PathRef) -> bool:
        """Whether any of the Ontology's patterns serves `path`."""
        return any(self.serves(p, path) for p in self.ontology.patterns)
