"""The Use Case YAML format, its canonical form and content hash.

    description: Support agents triage tickets          # optional
    competency_questions:
      - id: tickets-per-customer                       # required, unique
        question: Which tickets did a customer open?   # required, natural language
        query: MATCH (c:Customer)-[:OPENED]->(t:Ticket) RETURN t   # optional Cypher
        expected_answer: [{t: ...}]                    # optional, any JSON value
        concepts: [Customer, (Customer)-[OPENED]->(Ticket), Ticket.opened_at]  # optional
    consumers:                                         # optional
      - id: triage-bot                                 # required, unique among Consumers
        name: Triage bot                               # required
        kind: agent                                    # optional, free text
        contact: Ada Lovelace                          # optional, a name
        description: Routes new tickets                # optional
        tasks:                                         # optional
          - id: route-ticket                           # required, unique among all Tasks
            description: Route a ticket by its customer   # required
            competency_questions: [tickets-per-customer]  # ids of the questions it needs

The canonical form sorts questions, Consumers, Tasks and a Task's question ids, and
omits absent fields (`consumers` too, when there are none), so equal Use Cases hash
equally (identical content registers as the existing version).
"""

from __future__ import annotations

import json
from typing import Any, cast

import yaml

from stetiq import digest
from stetiq.errors import UseCaseValidationError
from stetiq.use_case.concepts import parse_concept_reference
from stetiq.use_case.model import CompetencyQuestion, Consumer, Task, UseCase

_TOP_LEVEL_KEYS = {"description", "competency_questions", "consumers"}
_QUESTION_KEYS = {"id", "question", "query", "expected_answer", "concepts"}
_CONSUMER_KEYS = {"id", "name", "kind", "contact", "description", "tasks"}
_TASK_KEYS = {"id", "description", "competency_questions"}


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
    consumers = tuple(
        _consumer(f"consumers[{i}]", c) for i, c in enumerate(_list(data, "consumers", "consumers"))
    )
    return check_use_case(
        UseCase(competency_questions=questions, description=description, consumers=consumers)
    )


def _list(raw: dict[str, Any], key: str, path: str) -> list[Any] | tuple[Any, ...]:
    value = raw.get(key, ())
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise UseCaseValidationError(f"{path}: must be a list")
    return value


def _mapping(path: str, raw: Any, keys: set[str], needs: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise UseCaseValidationError(f"{path}: expected a mapping with {needs}")
    unknown = set(raw) - keys
    if unknown:
        raise UseCaseValidationError(f"{path}: unknown keys {sorted(unknown)}")
    return raw


def _consumer(path: str, raw: Any) -> Consumer:
    raw = _mapping(path, raw, _CONSUMER_KEYS, "id and name")
    tasks = _list(raw, "tasks", f"{path}.tasks")
    # Unchecked YAML values: `check_use_case` validates them.
    return Consumer(
        id=cast(str, raw.get("id")),
        name=cast(str, raw.get("name")),
        kind=raw.get("kind"),
        contact=raw.get("contact"),
        description=raw.get("description"),
        tasks=tuple(_task(f"{path}.tasks[{i}]", t) for i, t in enumerate(tasks)),
    )


def _task(path: str, raw: Any) -> Task:
    raw = _mapping(path, raw, _TASK_KEYS, "id and description")
    return Task(
        id=cast(str, raw.get("id")),
        description=cast(str, raw.get("description")),
        competency_questions=tuple(
            _list(raw, "competency_questions", f"{path}.competency_questions")
        ),
    )


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
    # Unchecked YAML values: `check_question` (via `check_use_case`) validates them.
    return CompetencyQuestion(
        id=cast(str, raw.get("id")),
        question=cast(str, raw.get("question")),
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


def _check_id(id: Any, path: str) -> None:
    if not isinstance(id, str) or not id.strip():
        raise UseCaseValidationError(f"{path}.id: needs a non-empty string id")


def _check_text(value: Any, path: str, needs: str, *, required: bool = False) -> None:
    if (value is None and not required) or (isinstance(value, str) and value.strip()):
        return
    raise UseCaseValidationError(f"{path}: {needs}")


def _check_consumer(c: Consumer, question_ids: set[str], task_ids: set[str]) -> None:
    _check_id(c.id, "consumer")
    _check_text(c.name, f"{c.id}.name", "needs a name", required=True)
    for field in ("kind", "contact", "description"):
        _check_text(getattr(c, field), f"{c.id}.{field}", "must be a non-empty string")
    for t in c.tasks:
        _check_id(t.id, f"{c.id} task")
        if t.id in task_ids:
            raise UseCaseValidationError(f"{t.id}: duplicate task id")
        task_ids.add(t.id)
        _check_text(t.description, f"{t.id}.description", "needs a description", required=True)
        for q in t.competency_questions:
            if q not in question_ids:
                raise UseCaseValidationError(
                    f"{t.id}.competency_questions: unknown competency question {q!r}"
                )


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
    consumer_ids: set[str] = set()
    task_ids: set[str] = set()
    for c in use_case.consumers:
        _check_consumer(c, seen, task_ids)
        if c.id in consumer_ids:
            raise UseCaseValidationError(f"{c.id}: duplicate consumer id")
        consumer_ids.add(c.id)
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
    # Left out when empty, so a Use Case without Consumers hashes as it did before them.
    if use_case.consumers:
        d["consumers"] = [_consumer_dict(c) for c in sorted(use_case.consumers, key=lambda c: c.id)]
    return d


def _consumer_dict(c: Consumer) -> dict[str, Any]:
    d: dict[str, Any] = {"id": c.id, "name": c.name}
    for field in ("kind", "contact", "description"):
        if getattr(c, field) is not None:
            d[field] = getattr(c, field)
    if c.tasks:
        d["tasks"] = [_task_dict(t) for t in sorted(c.tasks, key=lambda t: t.id)]
    return d


def _task_dict(t: Task) -> dict[str, Any]:
    d: dict[str, Any] = {"id": t.id, "description": t.description}
    if t.competency_questions:
        d["competency_questions"] = sorted(t.competency_questions)
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
        consumers=tuple(
            Consumer(
                id=c["id"],
                name=c["name"],
                kind=c.get("kind"),
                contact=c.get("contact"),
                description=c.get("description"),
                tasks=tuple(
                    Task(
                        id=t["id"],
                        description=t["description"],
                        competency_questions=tuple(t.get("competency_questions", ())),
                    )
                    for t in c.get("tasks", ())
                ),
            )
            for c in d.get("consumers", ())
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
