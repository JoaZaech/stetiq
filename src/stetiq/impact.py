"""Consumer impact: which Consumers an Ontology Diff hits, through their Tasks' Competency
Questions. A pure function of an Ontology Diff, a Use Case and the Diff's base Ontology.

Each change is followed Concept -> Competency Question -> Task -> Consumer:

- a breaking change makes a question that needs its Concept **affected**;
- a deprecating change makes it **will be affected** (it still works, for now);
- cosmetic and additive changes hit nothing.

A question's Concepts are read the way structural answerability reads them: its explicit
`concepts` mapping, else its `query`. A question that states neither (only a question
mapper could map it) is **unknown** whenever the Diff breaks or deprecates anything, so it
is never reported as unaffected.

A change hits a requirement that names its Concept: a node or relationship type, or an
attribute, including one the requirement's owner inherits from (or passes down to) a
related node type in the base Ontology. A change to a relationship's endpoint pattern
hits only the paths that pattern can serve.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from stetiq.ontology.diff import Change, Classification, OntologyDiff
from stetiq.ontology.model import Ontology
from stetiq.use_case.concepts import (
    ConceptRef,
    NodeTypeRef,
    PathRef,
    PropertyRef,
    RelationshipTypeRef,
    Requirement,
)
from stetiq.use_case.model import CompetencyQuestion, UseCase
from stetiq.use_case.paths import PathIndex
from stetiq.use_case.requirements import stated_requirements

ImpactLevel = Literal["affected", "will_be_affected", "unknown"]

# Most severe first: a Task or Consumer takes the most severe level among its questions.
IMPACT_LEVELS: tuple[ImpactLevel, ...] = ("affected", "will_be_affected", "unknown")

_LEVEL_OF: dict[Classification, ImpactLevel] = {
    Classification.BREAKING: "affected",
    Classification.DEPRECATING: "will_be_affected",
}


@dataclass(frozen=True)
class QuestionImpact:
    """A Competency Question a change hits, and the changes that hit it (none when unknown)."""

    id: str
    question: str
    level: ImpactLevel
    changes: tuple[Change, ...] = ()


@dataclass(frozen=True)
class TaskImpact:
    id: str
    description: str
    level: ImpactLevel
    questions: tuple[QuestionImpact, ...]


@dataclass(frozen=True)
class ConsumerImpact:
    id: str
    name: str
    level: ImpactLevel
    tasks: tuple[TaskImpact, ...]
    kind: str | None = None


@dataclass(frozen=True)
class UseCaseImpact:
    """The Consumers a Diff hits, in Use Case order, each with only its hit Tasks and
    questions; `no_consumer` holds the hit questions no Task needs."""

    consumers: tuple[ConsumerImpact, ...] = ()
    no_consumer: tuple[QuestionImpact, ...] = ()

    def by_level(self, level: ImpactLevel) -> tuple[ConsumerImpact, ...]:
        return tuple(c for c in self.consumers if c.level == level)


def consumer_impact(diff: OntologyDiff, use_case: UseCase, base: Ontology) -> UseCaseImpact:
    """The Consumers, Tasks and Competency Questions of `use_case` that `diff` (whose base
    Ontology is `base`) hits."""
    relevant = [c for c in diff.changes if c.classification in _LEVEL_OF]
    index = PathIndex(base)
    questions = {
        q.id: impact
        for q in use_case.competency_questions
        if (impact := _question_impact(q, relevant, index)) is not None
    }
    consumers = []
    served: set[str] = set()
    for consumer in use_case.consumers:
        tasks = []
        for task in consumer.tasks:
            served.update(task.competency_questions)
            hit = tuple(questions[q] for q in task.competency_questions if q in questions)
            if hit:
                tasks.append(
                    TaskImpact(task.id, task.description, _most_severe(q.level for q in hit), hit)
                )
        if tasks:
            consumers.append(
                ConsumerImpact(
                    consumer.id,
                    consumer.name,
                    _most_severe(t.level for t in tasks),
                    tuple(tasks),
                    consumer.kind,
                )
            )
    return UseCaseImpact(
        tuple(consumers), tuple(q for id, q in questions.items() if id not in served)
    )


def _most_severe(levels: Iterable[ImpactLevel]) -> ImpactLevel:
    return min(levels, key=IMPACT_LEVELS.index)


def _question_impact(
    question: CompetencyQuestion, changes: list[Change], index: PathIndex
) -> QuestionImpact | None:
    source, required = stated_requirements(question)
    if source is None:
        return QuestionImpact(question.id, question.question, "unknown") if changes else None
    hits = tuple(c for c in changes if any(_hits(r, c, index) for r in required))
    if not hits:
        return None
    level = _most_severe(_LEVEL_OF[c.classification] for c in hits)
    return QuestionImpact(question.id, question.question, level, hits)


def _hits(req: Requirement, c: Change, index: PathIndex) -> bool:
    """Whether change `c` concerns what requirement `req` needs, in the Diff's base Ontology
    that `index` holds."""
    on_type = c.concept_kind != "property"
    match req:
        case ConceptRef(label):
            return on_type and c.concept == label
        case NodeTypeRef(label):
            return c.concept_kind == "node_type" and c.concept == label
        case RelationshipTypeRef(labels):
            return c.concept_kind == "relationship_type" and c.concept in labels
        case PropertyRef(owners, name):
            if on_type:
                return c.concept in owners
            related = {r for owner in owners for r in index.related(owner)}
            return c.attribute == name and c.owner in related
        case PathRef(source, relationships, target):
            if c.concept_kind == "node_type":
                return c.concept in (source, target)
            if c.concept_kind != "relationship_type" or (
                relationships and c.concept not in relationships
            ):
                return False
            if c.pattern is not None:  # an endpoint pattern change
                return index.serves(c.pattern, req)
            # A change to the relationship type itself hits a path naming it, and an open
            # path any of its base patterns serves.
            return bool(relationships) or any(
                index.serves(p, req) for p in index.ontology.patterns if p.relationship == c.concept
            )
    return False
