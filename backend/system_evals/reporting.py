from __future__ import annotations

import json
from typing import Any

from .schema import EvaluationResult, EvaluationRunSummary


def markdown_report(
    *,
    run_id: str,
    summary: EvaluationRunSummary | dict[str, Any],
    results: list[EvaluationResult] | list[dict[str, Any]],
) -> str:
    summary_payload = summary.as_dict() if hasattr(summary, "as_dict") else dict(summary)
    lines = [
        f"# System Evaluation Report: {run_id}",
        "",
        "## Summary",
        "",
        f"- Dataset: `{summary_payload.get('dataset_id', '')}`",
        f"- Total cases: {summary_payload.get('total_cases', 0)}",
        f"- Passed: {summary_payload.get('passed_cases', 0)}",
        f"- Failed: {summary_payload.get('failed_cases', 0)}",
        f"- Pass rate: {_pct(summary_payload.get('pass_rate', 0))}",
        f"- Average score: {_pct(summary_payload.get('average_score', 0))}",
        f"- Average latency: {summary_payload.get('average_latency_ms', 0)} ms",
        f"- Routing accuracy: {_pct(summary_payload.get('routing_accuracy', 0))}",
        f"- Tool accuracy: {_pct(summary_payload.get('tool_accuracy', 0))}",
        f"- Source accuracy: {_pct(summary_payload.get('source_accuracy', 0))}",
        f"- Safety accuracy: {_pct(summary_payload.get('safety_accuracy', 0))}",
        "",
        "## Cases",
        "",
    ]
    for raw in results:
        result = raw.as_dict() if hasattr(raw, "as_dict") else dict(raw)
        status = "PASS" if result.get("passed") else "FAIL"
        lines.extend(
            [
                f"### {status} - {result.get('case_id') or result.get('id')}",
                "",
                f"- Category: `{result.get('category', '')}`",
                f"- Score: {_pct(result.get('score', 0))}",
                f"- Latency: {result.get('latency_ms', 0)} ms",
                f"- Trace ID: `{result.get('trace_id', '')}`",
                f"- Agents: {', '.join(result.get('actual_agents') or []) or 'none'}",
                f"- Tools: {', '.join(result.get('actual_tools') or []) or 'none'}",
                f"- Sources: {', '.join(result.get('actual_sources') or []) or 'none'}",
            ]
        )
        failures = result.get("failure_reasons") or []
        if failures:
            lines.append(f"- Failures: {json.dumps(failures, ensure_ascii=False)}")
        lines.extend(["", "**Question**", "", str(result.get("query") or result.get("case", {}).get("query") or ""), "", "**Answer**", "", str(result.get("answer") or ""), ""])
    return "\n".join(lines)


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "0.0%"
