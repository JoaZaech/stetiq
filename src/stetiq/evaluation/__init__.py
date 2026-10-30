"""Evaluator framework (plug-in interface) and the built-in Evaluators."""

from stetiq.evaluation.alignment import GoldOntologyAlignment
from stetiq.evaluation.answerability import (
    ANSWERABILITY_EVALUATOR,
    CompetencyQuestionMapper,
    StructuralAnswerability,
)
from stetiq.evaluation.framework import (
    ConstructionRunEvaluator,
    ConstructionRunSubject,
    Detail,
    Evaluation,
    Evaluator,
    OntologyVersionEvaluator,
    ReadOnlyGraphSource,
    SubjectKind,
)
from stetiq.evaluation.llm_mapping import LlmMappingError, LlmQuestionMapper
from stetiq.evaluation.run import (
    CQ_EXECUTION_EVALUATOR,
    OBSERVED_SCHEMA_EVALUATOR,
    RUN_CONFORMANCE_EVALUATOR,
    matches_expected_answer,
)

__all__ = [
    "ANSWERABILITY_EVALUATOR",
    "CQ_EXECUTION_EVALUATOR",
    "OBSERVED_SCHEMA_EVALUATOR",
    "RUN_CONFORMANCE_EVALUATOR",
    "CompetencyQuestionMapper",
    "ConstructionRunEvaluator",
    "ConstructionRunSubject",
    "Detail",
    "Evaluation",
    "Evaluator",
    "GoldOntologyAlignment",
    "LlmMappingError",
    "LlmQuestionMapper",
    "OntologyVersionEvaluator",
    "ReadOnlyGraphSource",
    "StructuralAnswerability",
    "SubjectKind",
    "matches_expected_answer",
]
