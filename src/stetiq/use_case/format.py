"""The Use Case YAML format, its canonical form and content hash.

    description: Support agents triage tickets          # optional
    competency_questions:
      - id: tickets-per-customer                       # required, unique
        question: Which tickets did a customer open?   # required, natural language
        query: MATCH (c:Customer)-[:OPENED]->(t:Ticket) RETURN t   # optional Cypher
        expected_answer: [{t: ...}]                    # optional, any JSON value
        concepts: [Customer, (Customer)-[OPENED]->(Ticket), Ticket.opened_at]  # optional

The canonical form sorts questions by id and omits absent fields, so equal Use
Cases hash equally (identical content registers as the existing version).
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from stetiq import digest
from stetiq.errors import UseCaseValidationError
from stetiq.use_case.concepts import parse_concept_reference
from stetiq.use_case.model import CompetencyQuestion, UseCase

_TOP_LEVEL_KEYS = {"description", "competency_questions"}
_QUESTION_KEYS = {"id", "question", "query", "expected_answer", "concepts"}


def parse_use_case_yaml(text: str) -> UseCase:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise UseCaseValidationError(f"Use Case is not valid YAML: {e}") from None
    return parse_use_case_dict(data)


def parse_use_case_dict(data: Any) -> UseCase:
    """Validate a Use Case given as plain data; raises UseCaseValidationError naming the offending path."""
    if not isinstance(data, dict):
        raise UseCaseValidationError("Use Case: expected a mapping with competency_questions")
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise UseCaseValidationError(f"Use Case: unknown keys {sorted(unknown)}")
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise UseCaseValidationError("description: must be a string")
    raw = data.get("competency_questions")
    if not isinstance(raw, list) or not raw:
        raise UseCaseValidationError("competency_questions: needs at least one question")
    questions = tuple(_question(i, q) for i, q in enumerate(raw))
    return check_use_case(UseCase(competency_questions=questions, description=description))


def _question(index: int, raw: Any) -> CompetencyQuestion:
    path = f"competency_questions[{index}]"
    if not isinstance(raw, dict):
        raise UseCaseValidationError(f"{path}: expected a mapping with id and question")
    unknown = set(raw) - _QUESTION_KEYS
    if unknown:
        raise UseCaseValidationError(f"{path}: unknown keys {sorted(unknown)}")
    concepts = raw.get("concepts", ())
    if isinstance(concepts, str) or not isinstance(concepts, (list, tuple)):
        raise UseCaseValidationError(f"{path}.concepts: must be a list of Concept references")
    return CompetencyQuestion(
        id=raw.get("id"),
        question=raw.get("question"),
        query=raw.get("query"),
        expected_answer=raw.get("expected_answer"),
        concepts=tuple(concepts),
    )


def check_question(q: CompetencyQuestion, path: str | None = None) -> CompetencyQuestion:
    path = path or (q.id if isinstance(q.id, str) and q.id else "competency question")
    if not isinstance(q.id, str) or not q.id.strip():
        raise UseCaseValidationError(f"{path}.id: needs a non-empty string id")
    if not isinstance(q.question, str) or not q.question.strip():
        raise UseCaseValidationError(f"{path}.question: needs the question in natural language")
    if q.query is not None and (not isinstance(q.query, str) or not q.query.strip()):
        raise UseCaseValidationError(f"{path}.query: must be a non-empty Cypher string")
    try:
        json.dumps(q.expected_answer, allow_nan=False)
    except (TypeError, ValueError):
        raise UseCaseValidationError(
            f"{path}.expected_answer: must be a JSON value (strings, numbers, lists, mappings)"
        ) from None
    for c in q.concepts:
        if not isinstance(c, str):
            raise UseCaseValidationError(f"{path}.concepts: {c!r} is not a Concept reference")
        try:
            parse_concept_reference(c)
        except ValueError as e:
            raise UseCaseValidationError(f"{path}.concepts: {e}") from None
    return q


def check_use_case(use_case: UseCase) -> UseCase:
    """Validate a Use Case model (however it was built)."""
    if not use_case.competency_questions:
        raise UseCaseValidationError("competency_questions: needs at least one question")
    seen: set[str] = set()
    for q in use_case.competency_questions:
        check_question(q)
        if q.id in seen:
            raise UseCaseValidationError(f"{q.id}: duplicate competency question id")
        seen.add(q.id)
    return use_case


def to_dict(use_case: UseCase) -> dict[str, Any]:
    """The canonical dict form; also the shape of the YAML."""
    d: dict[str, Any] = {}
    if use_case.description is not None:
        d["description"] = use_case.description
    questions = []
    for q in sorted(use_case.competency_questions, key=lambda q: q.id):
        qd: dict[str, Any] = {"id": q.id, "question": q.question}
        if q.query is not None:
            qd["query"] = q.query
        if q.expected_answer is not None:
            qd["expected_answer"] = q.expected_answer
        if q.concepts:
            qd["concepts"] = list(q.concepts)
        questions.append(qd)
    d["competency_questions"] = questions
    return d


def from_dict(d: dict[str, Any]) -> UseCase:
    """Inverse of `to_dict`. Assumes validated input."""
    return UseCase(
        description=d.get("description"),
        competency_questions=tuple(
            CompetencyQuestion(
                id=q["id"],
                question=q["question"],
                query=q.get("query"),
                expected_answer=q.get("expected_answer"),
                concepts=tuple(q.get("concepts", ())),
            )
            for q in d["competency_questions"]
        ),
    )


def canonicalize(use_case: UseCase) -> UseCase:
    return from_dict(to_dict(use_case))


def canonical_json(use_case: UseCase) -> str:
    return digest.canonical_json(to_dict(use_case))


def from_canonical_json(text: str) -> UseCase:
    return from_dict(json.loads(text))


def content_hash(use_case: UseCase) -> str:
    return digest.content_hash(to_dict(use_case))


def to_yaml(use_case: UseCase) -> str:
    return yaml.safe_dump(to_dict(use_case), sort_keys=False, allow_unicode=True)
