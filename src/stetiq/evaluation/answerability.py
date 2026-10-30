"""Structural Competency Question answerability.

For every Competency Question of a Use Case, decide whether an Ontology Version
contains the Concepts and paths needed to answer it. What a question needs comes
from, in order of precedence:

1. its explicit Concept mapping (`concepts`),           source "concepts"
2. the Concepts and paths its Cypher `query` uses,      source "query"
3. a `CompetencyQuestionMapper` (the model interface),  source "model"

A question none of these can map is "unmapped" (not counted as answerable).

Matching is hierarchy-aware: a node type, its ancestors and its descendants can
all stand in for each other (a pattern on `Party` serves a question about
`Customer`, and vice versa). Deprecated Concepts still count as present.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from stetiq.evaluation.framework import Detail, Evaluation, OntologyVersionEvaluator
from stetiq.ontology import Ontology
from stetiq.use_case.concepts import (
    ConceptRef,
    NodeTypeRef,
    PathRef,
    PropertyRef,
    RelationshipTypeRef,
    Requirement,
    parse_concept_reference,
)
from stetiq.use_case.cypher import requirements_from_query
from stetiq.use_case.model import CompetencyQuestion, UseCase

ANSWERABILITY_EVALUATOR = "structural_answerability"


class CompetencyQuestionMapper(Protocol):
    """Maps a natural-language Competency Question onto an Ontology (e.g. with an LLM).

    Returns Concept references in the syntax of `CompetencyQuestion.concepts`
    (`Label`, `Owner.property`, `(Source)-[REL]->(Target)`), or an empty sequence
    if the question cannot be mapped. Only consulted for questions with neither a
    Concept mapping nor a query.

    A mapper may also expose a `description` (e.g. `"anthropic:claude-opus-5-5"`); it
    is stored with each question it mapped, as `data.mapper`.
    """

    def map_question(self, question: CompetencyQuestion, ontology: Ontology) -> Sequence[str]: ...


class _OntologyIndex:
    def __init__(self, ontology: Ontology) -> None:
        self.ontology = ontology
        self.nodes = {n.label: n for n in ontology.node_types}
        self.rels = {r.label: r for r in ontology.relationship_types}
        self._children: dict[str, list[str]] = {}
        for n in ontology.node_types:
            if n.parent:
                self._children.setdefault(n.parent, []).append(n.label)

    def related(self, label: str) -> set[str]:
        """The node type, its ancestors and its descendants."""
        out = {label}
        parent = self.nodes[label].parent if label in self.nodes else None
        while parent and parent not in out:
            out.add(parent)
            parent = self.nodes[parent].parent if parent in self.nodes else None
        stack = list(self._children.get(label, ()))
        while stack:
            child = stack.pop()
            if child not in out:
                out.add(child)
                stack.extend(self._children.get(child, ()))
        return out

    def missing(self, req: Requirement) -> list[Requirement]:
        """What `req` lacks in the Ontology: [] if satisfied, else the root causes."""
        match req:
            case ConceptRef(label):
                return [] if label in self.nodes or label in self.rels else [req]
            case NodeTypeRef(label):
                return [] if label in self.nodes else [req]
            case RelationshipTypeRef(labels):
                return [] if any(label in self.rels for label in labels) else [req]
            case PropertyRef(owners, name):
                known = [o for o in owners if o in self.nodes or o in self.rels]
                if not known:
                    return [ConceptRef(owners[0])] if len(owners) == 1 else [req]
                for owner in known:
                    concepts = (
                        [self.rels[owner]]
                        if owner in self.rels
                        else [self.nodes[n] for n in self.related(owner) if n in self.nodes]
                    )
                    if any(p.name == name for c in concepts for p in c.properties):
                        return []
                return [req]
            case PathRef(source, relationships, target, directed):
                parts: list[Requirement] = []
                for end in (source, target):
                    if end is not None and end not in self.nodes:
                        parts.append(NodeTypeRef(end))
                if relationships and not any(r in self.rels for r in relationships):
                    parts.append(RelationshipTypeRef(relationships))
                if parts:
                    return parts
                return [] if self._has_path(source, relationships, target, directed) else [req]
        raise TypeError(f"not a requirement: {req!r}")

    def _has_path(self, source, relationships, target, directed) -> bool:
        sources = self.related(source) if source else None
        targets = self.related(target) if target else None

        def fits(s: str, r: str, t: str) -> bool:
            return (
                (not relationships or r in relationships)
                and (sources is None or s in sources)
                and (targets is None or t in targets)
            )

        return any(
            fits(p.source, p.relationship, p.target)
            or (not directed and fits(p.target, p.relationship, p.source))
            for p in self.ontology.patterns
        )


class StructuralAnswerability(OntologyVersionEvaluator):
    """Per Competency Question: answerable, unanswerable (with the missing Concepts) or unmapped.

    Metrics: `questions`, `answerable_questions`, `unanswerable_questions`,
    `unmapped_questions`, `answerable_ratio`. One Detail per question (`item` = the
    question id, `metric` = the count it falls in) whose `data` is
    `{status, source, required, missing}` (Concept references as strings; plus
    `mapper` when a described mapper produced the mapping, and `error` when it failed).
    """

    name = ANSWERABILITY_EVALUATOR

    def __init__(self, use_case: UseCase, mapper: CompetencyQuestionMapper | None = None) -> None:
        self.use_case = use_case
        self.mapper = mapper

    def evaluate(self, version) -> Evaluation:
        index = _OntologyIndex(version.ontology)
        counts = {"answerable": 0, "unanswerable": 0, "unmapped": 0}
        details = []
        for question in sorted(self.use_case.competency_questions, key=lambda q: q.id):
            data = self._judge(question, index)
            counts[data["status"]] += 1
            details.append(
                Detail(
                    item=question.id,
                    message=_message(data),
                    metric=f"{data['status']}_questions",
                    data=data,
                )
            )
        total = len(self.use_case.competency_questions)
        return Evaluation(
            metrics={
                "questions": total,
                "answerable_questions": counts["answerable"],
                "unanswerable_questions": counts["unanswerable"],
                "unmapped_questions": counts["unmapped"],
                "answerable_ratio": counts["answerable"] / total if total else 1.0,
            },
            details=details,
        )

    def _requirements(
        self, question: CompetencyQuestion, ontology: Ontology
    ) -> tuple[str | None, list[Requirement], str | None]:
        if question.concepts:
            return "concepts", [parse_concept_reference(c) for c in question.concepts], None
        if question.query:
            found = requirements_from_query(question.query)
            if found:
                return "query", found, None
        if self.mapper is not None:
            try:
                mapped = [
                    parse_concept_reference(c) for c in self.mapper.map_question(question, ontology)
                ]
            except Exception as exc:  # noqa: BLE001 -- a model failure must not block versioning
                return None, [], f"mapper failed: {exc}"
            if mapped:
                return "model", mapped, None
        return None, [], None

    def _judge(self, question: CompetencyQuestion, index: _OntologyIndex) -> dict:
        source, required, error = self._requirements(question, index.ontology)
        missing: list[str] = []
        for req in required:
            for m in index.missing(req):
                if str(m) not in missing:
                    missing.append(str(m))
        status = "unmapped" if source is None else ("unanswerable" if missing else "answerable")
        data: dict = {
            "status": status,
            "source": source,
            "required": [str(r) for r in required],
            "missing": missing,
        }
        if source == "model" and getattr(self.mapper, "description", None):
            data["mapper"] = str(self.mapper.description)
        if error:
            data["error"] = error
        return data


def _message(data: dict) -> str:
    if data["status"] == "answerable":
        return "answerable"
    if data["status"] == "unanswerable":
        return "missing " + ", ".join(data["missing"])
    return data.get("error") or "no Concept mapping or query to map it onto the Ontology"
