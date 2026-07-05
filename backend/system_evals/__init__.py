"""System-level golden dataset evaluation helpers."""

from .dataset import bundled_dataset_ids, load_bundled_dataset, load_dataset
from .evaluator import ChatClient, EvaluationRunner, StaticChatClient, evaluate_response
from .reporting import markdown_report
from .schema import EvaluationCase, EvaluationResult, EvaluationRunSummary

__all__ = [
    "ChatClient",
    "EvaluationCase",
    "EvaluationResult",
    "EvaluationRunSummary",
    "EvaluationRunner",
    "StaticChatClient",
    "bundled_dataset_ids",
    "evaluate_response",
    "load_bundled_dataset",
    "load_dataset",
    "markdown_report",
]
