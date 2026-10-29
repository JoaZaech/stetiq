"""Evaluator framework (plug-in interface) and the built-in Evaluators."""

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

__all__ = [
    "ConstructionRunEvaluator",
    "ConstructionRunSubject",
    "Detail",
    "Evaluation",
    "Evaluator",
    "GoldOntologyAlignment",
    "OntologyVersionEvaluator",
    "ReadOnlyGraphSource",
    "SubjectKind",
]
