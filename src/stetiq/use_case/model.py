"""The Use Case model: Consumers, their Tasks and the Competency Questions those Tasks need,
versioned independently of the Ontology."""

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
class Task:
    """A piece of work one Consumer performs with the Knowledge Graph.

    - `id`: stable identifier, unique among all Tasks of the Use Case.
    - `description`: what the work is.
    - `competency_questions`: the ids of the Competency Questions it needs answered.
    """

    id: str
    description: str
    competency_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Consumer:
    """Anyone or anything that uses the Knowledge Graph downstream.

    - `id`: stable identifier across Use Case Versions, unique among the Consumers.
    - `name`: what people call it.
    - `kind`: optional free text (an application, an agent, a dashboard, a team, ...).
    - `contact`: optional name of whom to ask about it.
    - `description`: optional free text.
    - `tasks`: what it does with the Knowledge Graph. A Consumer depends on Concepts only
      through its Tasks' Competency Questions.
    """

    id: str
    name: str
    tasks: tuple[Task, ...] = ()
    kind: str | None = None
    contact: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class UseCase:
    competency_questions: tuple[CompetencyQuestion, ...]
    description: str | None = None
    consumers: tuple[Consumer, ...] = ()

    def competency_question(self, id: str) -> CompetencyQuestion:
        for q in self.competency_questions:
            if q.id == id:
                return q
        raise KeyError(id)
