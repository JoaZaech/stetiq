"""Consumer Gates: rules a Consumer declares in the Use Case for taking a new Ontology
Version, and their evaluation as a pure function.

A Consumer Gate judges what one Consumer would lose, against a baseline (the latest
finished Construction Run on the Contract Alias's Ontology Version), not absolute
health, so it is not a kind in the Gate registry (`stetiq.gates`). Its outcome has
the Gate outcome's shape (definition, passed, reasons) plus structured findings, so
the CLI and the web UI render both the same way. Only `row_count_drop` is built::

    consumer_gates:
      - name: triage-rows-hold      # optional; defaults to the check
        check: row_count_drop
        task: triage-breakdowns     # one of this Consumer's Tasks
        max_drop: 0.10              # fraction 0-1

A verdict names the symptom (Task, Competency Question, row change), never a cause
(ADR 0001). The row counts are the ones `competency_question_execution` recorded; the
rows themselves never reach this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from stetiq import gates
from stetiq.errors import ConsumerGateConfigError

ROW_COUNT_DROP = "row_count_drop"
# Kinds the Connector spec names that are not built yet.
PLANNED_CHECKS = ("consumer_impact", "conformance", "observed_count", "fill_rate", "task_questions")


@dataclass(frozen=True)
class RowCountDropGate:
    """For each Competency Question of `task`, the executed row count may not drop by
    more than `max_drop` (a fraction, 0.1 = 10%) from the baseline run's. A question
    without a row count on either side fails; a baseline of 0 rows cannot drop."""

    task: str
    max_drop: float
    name: str = ROW_COUNT_DROP
    check: ClassVar[str] = ROW_COUNT_DROP

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "check": self.check,
            "task": self.task,
            "max_drop": float(self.max_drop),
        }


_ROW_COUNT_DROP_KEYS = {"name", "check", "task", "max_drop"}


def parse_consumer_gate(path: str, raw: Any) -> RowCountDropGate:
    """One `consumer_gates` entry. Checks its shape; `check_consumer_gates` checks its values."""
    if not isinstance(raw, dict):
        raise ConsumerGateConfigError(f"{path}: expected a mapping with check, task and max_drop")
    check = raw.get("check")
    if check in PLANNED_CHECKS:
        raise ConsumerGateConfigError(
            f"{path}.check: {check!r} is planned but not built yet (built: {ROW_COUNT_DROP})"
        )
    if check != ROW_COUNT_DROP:
        raise ConsumerGateConfigError(
            f"{path}.check: unknown check {check!r} (expected {ROW_COUNT_DROP})"
        )
    unknown = set(raw) - _ROW_COUNT_DROP_KEYS
    if unknown:
        raise ConsumerGateConfigError(f"{path}: unknown keys {sorted(unknown)}")
    for key in ("task", "max_drop"):
        if key not in raw:
            raise ConsumerGateConfigError(f"{path}: missing {key!r}")
    # Unchecked YAML values: `check_consumer_gates` validates them.
    return RowCountDropGate(
        name=raw.get("name", ROW_COUNT_DROP), task=raw["task"], max_drop=raw["max_drop"]
    )


def check_consumer_gates(consumer: str, gates: Sequence[Any], task_ids: set[str]) -> None:
    """The values of one Consumer's Consumer Gates, however they were built."""
    names: set[str] = set()
    for i, gate in enumerate(gates):
        path = f"{consumer}.consumer_gates[{i}]"
        if not isinstance(gate, RowCountDropGate):
            raise ConsumerGateConfigError(f"{path}: not a Consumer Gate ({gate!r})")
        if not isinstance(gate.name, str) or not gate.name.strip():
            raise ConsumerGateConfigError(f"{path}.name: must be a non-empty string")
        if gate.name in names:
            raise ConsumerGateConfigError(
                f"{path}.name: duplicate Consumer Gate name {gate.name!r}"
            )
        names.add(gate.name)
        if gate.task not in task_ids:
            raise ConsumerGateConfigError(
                f"{path}.task: {gate.task!r} is not a Task of Consumer {consumer!r}"
            )
        drop = gate.max_drop
        if isinstance(drop, bool) or not isinstance(drop, (int, float)) or not 0 <= drop <= 1:
            raise ConsumerGateConfigError(f"{path}.max_drop: must be a number between 0 and 1")


def consumer_gate_from_dict(d: Mapping[str, Any]) -> RowCountDropGate:
    """Inverse of `to_dict`. Assumes validated input."""
    return RowCountDropGate(name=d["name"], task=d["task"], max_drop=float(d["max_drop"]))


# --- Evaluation --------------------------------------------------------------------------

# Why a question has no row change: no baseline run at all, or no result / an errored
# query on one side ("missing" also covers a question without a query, never executed).
MissingInput = Literal[
    "no_baseline_run", "baseline_missing", "baseline_error", "candidate_missing", "candidate_error"
]


@dataclass(frozen=True)
class QuestionRows:
    """One executed Competency Question's recorded row count on a run."""

    rows: int
    error: bool = False


@dataclass(frozen=True)
class RowCountFinding:
    """A failing question of a `row_count_drop` gate, as fields (no code parses
    `reasons`). `change` is relative, (after - before) / before, so a drop is negative;
    `limit` is the gate's `max_drop`. With `missing` set, the counts that exist are
    given and `change` is None."""

    task: str
    competency_question: str
    limit: float
    before: int | None = None
    after: int | None = None
    change: float | None = None
    missing: MissingInput | None = None


@dataclass(frozen=True)
class ConsumerGateOutcome:
    gate: RowCountDropGate
    passed: bool
    reasons: tuple[str, ...] = ()
    findings: tuple[RowCountFinding, ...] = ()


@dataclass(frozen=True)
class ConsumerGateInputs:
    """The row counts of the Candidate run and the baseline run (None: no baseline run),
    by Competency Question id. `baseline_version` is the Contract Alias's version, None
    when it points to none."""

    task_questions: Mapping[str, Sequence[str]]  # Task id -> its Competency Question ids
    candidate: Mapping[str, QuestionRows]
    baseline: Mapping[str, QuestionRows] | None
    baseline_version: int | None


def evaluate_consumer_gate(
    gate: RowCountDropGate, inputs: ConsumerGateInputs
) -> ConsumerGateOutcome:
    questions = inputs.task_questions.get(gate.task, ())
    limit = float(gate.max_drop)
    if not questions:
        return ConsumerGateOutcome(
            gate,
            False,
            (f"Task {gate.task!r} needs no Competency Question, so nothing can be compared",),
        )
    if inputs.baseline is None:
        findings = tuple(
            RowCountFinding(
                task=gate.task,
                competency_question=q,
                limit=limit,
                after=_rows(inputs.candidate.get(q)),
                missing="no_baseline_run",
            )
            for q in questions
        )
        return ConsumerGateOutcome(
            gate,
            False,
            (
                "No baseline: the Contract Alias points to no Ontology Version"
                if inputs.baseline_version is None
                else f"No baseline: no finished Construction Run on Ontology Version "
                f"{inputs.baseline_version} (the Contract Alias's) to compare with",
            ),
            findings,
        )
    findings_list: list[RowCountFinding] = []
    reasons: list[str] = []
    for q in questions:
        before, after = inputs.baseline.get(q), inputs.candidate.get(q)
        missing = _missing(before, after)
        if missing is not None:
            findings_list.append(
                RowCountFinding(
                    task=gate.task,
                    competency_question=q,
                    limit=limit,
                    before=_rows(before),
                    after=_rows(after),
                    missing=missing,
                )
            )
            reasons.append(f"{gate.task} / {q}: {_MISSING_TEXT[missing]}")
            continue
        assert before is not None and after is not None
        if before.rows == 0:
            continue
        change = (after.rows - before.rows) / before.rows
        if -change > limit:
            findings_list.append(
                RowCountFinding(
                    task=gate.task,
                    competency_question=q,
                    limit=limit,
                    before=before.rows,
                    after=after.rows,
                    change=change,
                )
            )
            reasons.append(
                f"{gate.task} / {q}: {before.rows} → {after.rows} rows "
                f"({_MINUS}{-change * 100:.1f}%, limit {_MINUS}{limit * 100:g}%)"
            )
    return ConsumerGateOutcome(gate, not findings_list, tuple(reasons), tuple(findings_list))


_MINUS = "\u2212"  # MINUS SIGN, as a drop reads in the CLI and the web UI

_MISSING_TEXT: dict[str, str] = {
    "baseline_missing": "no row count on the baseline run (not executed: no query, or not in "
    "its Use Case)",
    "baseline_error": "the query failed on the baseline run",
    "candidate_missing": "no row count on the Candidate run (not executed: no query, or not "
    "in its Use Case)",
    "candidate_error": "the query failed on the Candidate run",
}


def _rows(q: QuestionRows | None) -> int | None:
    return None if q is None or q.error else q.rows


def _missing(before: QuestionRows | None, after: QuestionRows | None) -> MissingInput | None:
    if before is None:
        return "baseline_missing"
    if before.error:
        return "baseline_error"
    if after is None:
        return "candidate_missing"
    if after.error:
        return "candidate_error"
    return None


def outcome_to_dict(o: ConsumerGateOutcome) -> dict[str, Any]:
    """A Gate outcome's form (`gates.outcome_to_dict`) plus `findings`."""
    return {**gates.outcome_to_dict(o), "findings": [_finding_to_dict(f) for f in o.findings]}


def outcome_from_dict(d: Mapping[str, Any]) -> ConsumerGateOutcome:
    passed, reasons = gates.verdict_from_dict(d)
    return ConsumerGateOutcome(
        gate=consumer_gate_from_dict(d["gate"]),
        passed=passed,
        reasons=reasons,
        findings=tuple(_finding_from_dict(f) for f in d.get("findings", ())),
    )


def _finding_to_dict(f: RowCountFinding) -> dict[str, Any]:
    d: dict[str, Any] = {
        "task": f.task,
        "competency_question": f.competency_question,
        "limit": f.limit,
    }
    for key in ("before", "after", "change", "missing"):
        if getattr(f, key) is not None:
            d[key] = getattr(f, key)
    return d


def _finding_from_dict(d: Mapping[str, Any]) -> RowCountFinding:
    return RowCountFinding(
        task=d["task"],
        competency_question=d["competency_question"],
        limit=float(d["limit"]),
        before=d.get("before"),
        after=d.get("after"),
        change=d.get("change"),
        missing=d.get("missing"),
    )
