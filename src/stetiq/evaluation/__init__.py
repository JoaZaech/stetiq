"""Evaluator framework (plug-in interface) and the built-in Evaluators."""

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
from stetiq.evaluation.alignment import GoldOntologyAlignment
from stetiq.evaluation.llm_mapping import LlmMappingError, LlmQuestionMapper

__all__ = [
    "ANSWERABILITY_EVALUATOR",
    "CompetencyQuestionMapper",
    "StructuralAnswerability",
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
    "SubjectKind",
]
