"""What a Competency Question says it needs, read without a model."""

from __future__ import annotations

from typing import Literal

from stetiq.use_case.concepts import Requirement, parse_concept_reference
from stetiq.use_case.cypher import requirements_from_query
from stetiq.use_case.model import CompetencyQuestion

StatedSource = Literal["concepts", "query"]


def stated_requirements(
    question: CompetencyQuestion,
) -> tuple[StatedSource | None, list[Requirement]]:
    """The question's explicit Concept mapping, else the Concepts and paths its `query`
    uses; `(None, [])` when it states neither (only a question mapper could map it)."""
    if question.concepts:
        return "concepts", [parse_concept_reference(c) for c in question.concepts]
    if question.query:
        found = requirements_from_query(question.query)
        if found:
            return "query", found
    return None, []
