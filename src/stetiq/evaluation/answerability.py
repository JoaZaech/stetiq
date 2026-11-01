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

A question is "regressed" when the Contract Alias's Ontology Version answers it but
the judged version does not, so a Gate can block a Promotion that would stop
answering it.

`competency_question_coverage` reads the same Concept mapping the other way round: which
Concepts of the version no Competency Question references. It shares the mapping (and
so the mapper's answers) with `structural_answerability`, so the two always agree.

`unjustified_additions` reads that mapping too, for an evolving run's Candidate: which
Concepts the Candidate adds to the version its run consumed that no question needs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from stetiq.evaluation.framework import Detail, Evaluation, OntologyVersionEvaluator
from stetiq.ontology import Ontology
from stetiq.ontology.diff import ChangeKind, diff_ontologies
from stetiq.ontology.model import ConceptKind, live_concepts
from stetiq.use_case.concepts import (
    ConceptRef,
    NodeTypeRef,
    PathRef,
    PropertyRef,
    RelationshipTypeRef,
    Requirement,
    parse_concept_reference,
)
from stetiq.use_case.model import CompetencyQuestion, UseCase
from stetiq.use_case.paths import PathIndex
from stetiq.use_case.requirements import stated_requirements

if TYPE_CHECKING:
    from stetiq.tracking.entities import OntologyVersion

ANSWERABILITY_EVALUATOR = "structural_answerability"
COVERAGE_EVALUATOR = "competency_question_coverage"
UNJUSTIFIED_ADDITIONS_EVALUATOR = "unjustified_additions"


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


class _OntologyIndex(PathIndex):
    def __init__(self, ontology: Ontology) -> None:
        super().__init__(ontology)
        self.nodes = {n.label: n for n in ontology.node_types}
        self.rels = {r.label: r for r in ontology.relationship_types}

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
            case PathRef(source, relationships, target):
                parts: list[Requirement] = []
                for end in (source, target):
                    if end is not None and end not in self.nodes:
                        parts.append(NodeTypeRef(end))
                if relationships and not any(r in self.rels for r in relationships):
                    parts.append(RelationshipTypeRef(relationships))
                if parts:
                    return parts
                return [] if self.has_path(req) else [req]
        raise TypeError(f"not a requirement: {req!r}")

    def referenced(self, req: Requirement) -> set[tuple[ConceptKind, str]]:
        """The Concepts of the Ontology that `req` names, as (kind, identity) pairs.

        An attribute is identified as `Owner.name`; one named on a node type is found on
        the node type, its ancestors or its descendants, as `missing` matches it."""
        match req:
            case ConceptRef(label) | NodeTypeRef(label):
                out: set[tuple[ConceptKind, str]] = set()
                if label in self.nodes:
                    out.add(("node_type", label))
                if isinstance(req, ConceptRef) and label in self.rels:
                    out.add(("relationship_type", label))
                return out
            case RelationshipTypeRef(labels):
                return {("relationship_type", label) for label in labels if label in self.rels}
            case PropertyRef(owners, name):
                out = set()
                for owner in owners:
                    if owner in self.rels:
                        out.add(("relationship_type", owner))
                        if any(p.name == name for p in self.rels[owner].properties):
                            out.add(("property", f"{owner}.{name}"))
                    elif owner in self.nodes:
                        out.add(("node_type", owner))
                        for node in self.related(owner):
                            if node in self.nodes and any(
                                p.name == name for p in self.nodes[node].properties
                            ):
                                out.add(("property", f"{node}.{name}"))
                return out
            case PathRef(source, relationships, target, _):
                out = {("node_type", end) for end in (source, target) if end in self.nodes}
                out.update(("relationship_type", r) for r in relationships if r in self.rels)
                return out
        raise TypeError(f"not a requirement: {req!r}")


class StructuralAnswerability(OntologyVersionEvaluator):
    """Per Competency Question: answerable, unanswerable (with the missing Concepts) or unmapped.

    Metrics: `questions`, `answerable_questions`, `unanswerable_questions`,
    `unmapped_questions`, `answerable_ratio`, and `questions_serving_no_task` (the
    questions no Consumer's Task needs: all of them in a Use Case without Consumers). One Detail per question (`item` = the
    question id, `metric` = the count it falls in) whose `data` is
    `{status, source, required, missing}` (Concept references as strings; plus
    `mapper` when a described mapper produced the mapping, and `error` when it failed).

    `regressed_questions` counts the questions `contract` (the Contract Alias's
    Ontology Version) answers but the judged version does not; it is 0 without a
    `contract` or when the judged version is the contract. Each regressed question
    gets a second Detail (`metric` = `regressed_questions`) whose `data` is
    `{status: "regressed", contract_version, missing}`.
    """

    name = ANSWERABILITY_EVALUATOR

    def __init__(
        self,
        use_case: UseCase,
        mapper: CompetencyQuestionMapper | None = None,
        contract: OntologyVersion | None = None,
    ) -> None:
        self.use_case = use_case
        self.mapper = mapper
        self.contract = contract
        # Each question is mapped once per Ontology, however many Evaluators read it.
        self._mappings: dict[int, tuple[Ontology, dict]] = {}

    def evaluate(self, version) -> Evaluation:
        index = _OntologyIndex(version.ontology)
        # Regressions are judged against the Contract Alias's version, unless this is it.
        contract = self.contract
        if contract is not None and contract.number == version.number:
            contract = None
        contract_index = None if contract is None else _OntologyIndex(contract.ontology)
        counts = {"answerable": 0, "unanswerable": 0, "unmapped": 0}
        details = []
        regressions = []
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
            if (
                contract is not None
                and contract_index is not None
                and data["status"] != "answerable"
                and self._judge(question, contract_index)["status"] == "answerable"
            ):
                regressions.append(
                    Detail(
                        item=question.id,
                        message=_regression_message(contract.number, data["missing"]),
                        metric="regressed_questions",
                        data={
                            "status": "regressed",
                            "contract_version": contract.number,
                            "missing": data["missing"],
                        },
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
                "regressed_questions": len(regressions),
                "questions_serving_no_task": sum(
                    not self.use_case.serving(q.id) for q in self.use_case.competency_questions
                ),
            },
            details=details + regressions,
        )

    def concept_mapping(
        self, ontology: Ontology
    ) -> dict[str, tuple[str | None, list[Requirement], str | None]]:
        """Per question id: (source, requirements, mapper error) against `ontology`."""
        cached = self._mappings.get(id(ontology))
        if cached is None or cached[0] is not ontology:
            mapping = {
                q.id: self._map(q, ontology)
                for q in sorted(self.use_case.competency_questions, key=lambda q: q.id)
            }
            cached = self._mappings[id(ontology)] = (ontology, mapping)
        return cached[1]

    def _map(
        self, question: CompetencyQuestion, ontology: Ontology
    ) -> tuple[str | None, list[Requirement], str | None]:
        source, stated = stated_requirements(question)
        if source is not None:
            return source, stated, None
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
        source, required, error = self.concept_mapping(index.ontology)[question.id]
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
        description = getattr(self.mapper, "description", None)
        if source == "model" and description:
            data["mapper"] = str(description)
        if error:
            data["error"] = error
        return data


class CompetencyQuestionCoverage(OntologyVersionEvaluator):
    """Which Concepts of the version no Competency Question references.

    Metrics: `concepts`, `traced_concepts`, `untraced_concepts`, `traced_concept_ratio`
    (1.0 for an Ontology without Concepts). One Detail per untraced Concept (`item` =
    `Label` or `Owner.attribute`, `metric` = `untraced_concepts`, `data` = `{kind}`).
    Deprecated Concepts, and the attributes of deprecated classes and relations, are
    left out of every count. It reads `answerability`'s Concept mapping.
    """

    name = COVERAGE_EVALUATOR

    def __init__(self, answerability: StructuralAnswerability) -> None:
        self.answerability = answerability

    def evaluate(self, version) -> Evaluation:
        ontology = version.ontology
        index = _OntologyIndex(ontology)
        traced: set[tuple[ConceptKind, str]] = set()
        for _, required, _ in self.answerability.concept_mapping(ontology).values():
            for req in required:
                traced |= index.referenced(req)
        concepts = [(kind, identity) for kind, identity, _ in live_concepts(ontology)]
        untraced = [c for c in concepts if c not in traced]
        total = len(concepts)
        return Evaluation(
            metrics={
                "concepts": total,
                "traced_concepts": total - len(untraced),
                "untraced_concepts": len(untraced),
                "traced_concept_ratio": (total - len(untraced)) / total if total else 1.0,
            },
            details=[
                Detail(
                    item=identity,
                    message="no Competency Question references it",
                    metric="untraced_concepts",
                    data={"kind": kind},
                )
                for kind, identity in untraced
            ],
        )


class UnjustifiedAdditions(OntologyVersionEvaluator):
    """Which Concepts an evolving run's Candidate adds that no Competency Question needs.

    `base` is the Ontology the run consumed; the added Concepts are the Ontology Diff's
    additions from it to the judged version: Classes and Relations (each with its
    Attributes) and Attributes added to a declared Class or Relation. Added Vocabulary
    Values are left out. An added Class or Relation is justified when a question's
    Concept requirements (as `answerability` maps them, so including mapped questions)
    name it; an added Attribute when they name it or when its owner is an added,
    justified Concept. An unmapped question justifies nothing, and without a Use Case
    (`answerability` None) nothing is justified.

    Metrics: `unjustified_additions`, `added_concepts`, `justified_ratio` (1.0 when
    nothing was added). One Detail per unjustified Concept (`item` = `Label` or
    `Owner.attribute`, `metric` = `unjustified_additions`, `data` = `{kind}`). Without
    a `base` (a version that is not a run's Candidate) nothing counts as added.
    """

    name = UNJUSTIFIED_ADDITIONS_EVALUATOR

    def __init__(
        self, answerability: StructuralAnswerability | None, base: Ontology | None
    ) -> None:
        self.answerability = answerability
        self.base = base

    def evaluate(self, version) -> Evaluation:
        ontology = version.ontology
        added = [] if self.base is None else _added_concepts(self.base, ontology)
        needed: set[tuple[ConceptKind, str]] = set()
        if self.answerability is not None:
            index = _OntologyIndex(ontology)
            for _, required, _ in self.answerability.concept_mapping(ontology).values():
                for req in required:
                    needed |= index.referenced(req)
        added_keys = {a.key for a in added}
        unjustified = [
            a
            for a in added
            if a.key not in needed
            and not (a.owner is not None and a.owner in added_keys and a.owner in needed)
        ]
        total = len(added)
        return Evaluation(
            metrics={
                "unjustified_additions": len(unjustified),
                "added_concepts": total,
                "justified_ratio": (total - len(unjustified)) / total if total else 1.0,
            },
            details=[
                Detail(
                    item=a.identity,
                    message="added, but no Competency Question needs it",
                    metric="unjustified_additions",
                    data={"kind": a.kind},
                )
                for a in unjustified
            ],
        )


@dataclass(frozen=True)
class _AddedConcept:
    """A Concept the Ontology Diff adds; `owner` is the (kind, identity) of the added
    Class or Relation an Attribute belongs to, or of the declared one it was added to."""

    kind: ConceptKind
    identity: str
    owner: tuple[ConceptKind, str] | None = None

    @property
    def key(self) -> tuple[ConceptKind, str]:
        return (self.kind, self.identity)


def _added_concepts(base: Ontology, target: Ontology) -> list[_AddedConcept]:
    """Every Concept the diff from `base` to `target` adds; an added Class or Relation
    brings its own Attributes, owned by it."""
    owners = {
        **{("node_type", n.label): n for n in target.node_types},
        **{("relationship_type", r.label): r for r in target.relationship_types},
    }
    added: list[_AddedConcept] = []
    for change in diff_ontologies(base, target).changes:
        if change.kind != ChangeKind.ADDED:
            continue
        if change.concept_kind in ("node_type", "relationship_type"):
            concept = _AddedConcept(change.concept_kind, change.concept)
            added.append(concept)
            added += [
                _AddedConcept("property", f"{change.concept}.{p.name}", concept.key)
                for p in owners[concept.key].properties
            ]
        elif change.concept_kind == "property" and change.owner and change.owner_kind:
            added.append(
                _AddedConcept("property", change.concept, (change.owner_kind, change.owner))
            )
    return added


def _regression_message(contract_version: int, missing: list[str]) -> str:
    message = f"answered by Ontology Version {contract_version}"
    return message + (", missing " + ", ".join(missing) if missing else "")


def _message(data: dict) -> str:
    if data["status"] == "answerable":
        return "answerable"
    if data["status"] == "unanswerable":
        return "missing " + ", ".join(data["missing"])
    return data.get("error") or "no Concept mapping or query to map it onto the Ontology"
