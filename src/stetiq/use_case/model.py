"""The Use Case model: a set of Competency Questions, versioned independently of the Ontology."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompetencyQuestion:
    """A domain question the Knowledge Graph must be able to answer.

    - `id`: stable identifier, unique within the Use Case (what results and Gates refer to).
    - `question`: the natural-language question.
    - `query`: optional Cypher query answering it (structural answerability reads its
      Concepts and paths; run-level evaluation executes it against the Graph Source).
    - `expected_answer`: optional JSON value the executed query's rows must match.
    - `concepts`: optional explicit Concept mapping, in Concept-reference syntax:
      `Customer` (node or relationship type), `Ticket.opened_at` (attribute),
      `(Customer)-[OPENED]->(Ticket)` (path; `()` / `[]` leave an end open).
      When given, it takes precedence over what is read from `query`.
    """

    id: str
    question: str
    query: str | None = None
    expected_answer: Any = None
    concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class UseCase:
    competency_questions: tuple[CompetencyQuestion, ...]
    description: str | None = None

    def competency_question(self, id: str) -> CompetencyQuestion:
        for q in self.competency_questions:
            if q.id == id:
                return q
        raise KeyError(id)
