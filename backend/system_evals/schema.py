from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    category: str
    query: str
    user: str = "admin"
    expected_agents: tuple[str, ...] = ()
    expected_tools: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    required_answer_patterns: tuple[str, ...] = ()
    forbidden_answer_patterns: tuple[str, ...] = ()
    required_safety_flags: tuple[str, ...] = ()
    max_latency_ms: int = 30000
    minimum_score: float = 1.0
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvaluationCase":
        return cls(
            id=str(payload.get("id") or "").strip(),
            category=str(payload.get("category") or "uncategorized").strip(),
            query=str(payload.get("query") or "").strip(),
            user=str(payload.get("user") or "admin").strip(),
            expected_agents=_string_tuple(payload.get("expected_agents")),
            expected_tools=_string_tuple(payload.get("expected_tools")),
            expected_sources=_string_tuple(payload.get("expected_sources")),
            required_answer_patterns=_string_tuple(payload.get("required_answer_patterns")),
            forbidden_answer_patterns=_string_tuple(payload.get("forbidden_answer_patterns")),
            required_safety_flags=_string_tuple(payload.get("required_safety_flags")),
            max_latency_ms=int(payload.get("max_latency_ms") or 30000),
            minimum_score=float(payload.get("minimum_score") if payload.get("minimum_score") is not None else 1.0),
            notes=str(payload.get("notes") or ""),
        )

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Evaluation case is missing id")
        if not self.query:
            raise ValueError(f"Evaluation case {self.id} is missing query")
        if self.minimum_score < 0 or self.minimum_score > 1:
            raise ValueError(f"Evaluation case {self.id} minimum_score must be between 0 and 1")
        if self.max_latency_ms < 1:
            raise ValueError(f"Evaluation case {self.id} max_latency_ms must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "query": self.query,
            "user": self.user,
            "expected_agents": list(self.expected_agents),
            "expected_tools": list(self.expected_tools),
            "expected_sources": list(self.expected_sources),
            "required_answer_patterns": list(self.required_answer_patterns),
            "forbidden_answer_patterns": list(self.forbidden_answer_patterns),
            "required_safety_flags": list(self.required_safety_flags),
            "max_latency_ms": self.max_latency_ms,
            "minimum_score": self.minimum_score,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class EvaluationResult:
    case: EvaluationCase
    passed: bool
    score: float
    failure_reasons: tuple[str, ...] = ()
    answer: str = ""
    response: dict[str, Any] = field(default_factory=dict)
    actual_agents: tuple[str, ...] = ()
    actual_tools: tuple[str, ...] = ()
    actual_sources: tuple[str, ...] = ()
    safety_flags: tuple[str, ...] = ()
    latency_ms: int = 0
    trace_id: str = ""
    tool_execution_location: str = ""
    tool_execution_records: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.as_dict(),
            "case_id": self.case.id,
            "category": self.case.category,
            "query": self.case.query,
            "user": self.case.user,
            "passed": self.passed,
            "score": self.score,
            "failure_reasons": list(self.failure_reasons),
            "answer": self.answer,
            "response": self.response,
            "actual_agents": list(self.actual_agents),
            "actual_tools": list(self.actual_tools),
            "actual_sources": list(self.actual_sources),
            "safety_flags": list(self.safety_flags),
            "latency_ms": self.latency_ms,
            "trace_id": self.trace_id,
            "tool_execution_location": self.tool_execution_location,
            "tool_execution_records": list(self.tool_execution_records),
        }


@dataclass(frozen=True)
class EvaluationRunSummary:
    dataset_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    average_score: float
    average_latency_ms: int
    routing_accuracy: float
    tool_accuracy: float
    source_accuracy: float
    safety_accuracy: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "pass_rate": self.pass_rate,
            "average_score": self.average_score,
            "average_latency_ms": self.average_latency_ms,
            "routing_accuracy": self.routing_accuracy,
            "tool_accuracy": self.tool_accuracy,
            "source_accuracy": self.source_accuracy,
            "safety_accuracy": self.safety_accuracy,
        }


def summarize_results(dataset_id: str, results: list[EvaluationResult]) -> EvaluationRunSummary:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    latencies = [result.latency_ms for result in results if result.latency_ms > 0]
    return EvaluationRunSummary(
        dataset_id=dataset_id,
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        pass_rate=(passed / total) if total else 0.0,
        average_score=(sum(result.score for result in results) / total) if total else 0.0,
        average_latency_ms=int(sum(latencies) / len(latencies)) if latencies else 0,
        routing_accuracy=_expectation_accuracy(results, "expected_agents", "actual_agents"),
        tool_accuracy=_expectation_accuracy(results, "expected_tools", "actual_tools"),
        source_accuracy=_expectation_accuracy(results, "expected_sources", "actual_sources"),
        safety_accuracy=_expectation_accuracy(results, "required_safety_flags", "safety_flags"),
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _expectation_accuracy(results: list[EvaluationResult], expected_attr: str, actual_attr: str) -> float:
    applicable = []
    for result in results:
        expected = tuple(getattr(result.case, expected_attr))
        if expected:
            applicable.append((expected, tuple(getattr(result, actual_attr))))
    if not applicable:
        return 1.0
    matches = 0
    for expected, actual in applicable:
        if all(_contains_casefold(actual, item) for item in expected):
            matches += 1
    return matches / len(applicable)


def _contains_casefold(values: tuple[str, ...], needle: str) -> bool:
    needle_lower = needle.lower()
    return any(needle_lower in value.lower() for value in values)
