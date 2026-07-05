from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .schema import EvaluationCase, EvaluationResult


class ChatClient(Protocol):
    def ask(self, case: EvaluationCase) -> dict[str, Any]:
        ...


@dataclass
class StaticChatClient:
    responses: dict[str, dict[str, Any]]

    def ask(self, case: EvaluationCase) -> dict[str, Any]:
        return dict(self.responses.get(case.id) or {})


class HttpChatClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds
        self._token: str | None = None

    def ask(self, case: EvaluationCase) -> dict[str, Any]:
        token = self._token or self._login()
        payload = {
            "query": case.query,
            "session_id": f"system-eval-http-{case.id}-{int(time.time())}",
        }
        return self._post_json("/chat", payload, token=token)

    def _login(self) -> str:
        payload = self._post_json(
            "/auth/login",
            {"username": self.username, "password": self.password},
            token=None,
        )
        token = str(payload.get("access_token") or "")
        if not token:
            raise RuntimeError("Login succeeded but no access_token was returned")
        self._token = token
        return token

    def _post_json(self, path: str, payload: dict[str, Any], *, token: str | None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{exc.code} {exc.reason}: {body}") from exc


class EvaluationRunner:
    def __init__(self, client: ChatClient):
        self.client = client

    def run(self, cases: list[EvaluationCase]) -> list[EvaluationResult]:
        results = []
        for case in cases:
            started = time.perf_counter()
            try:
                response = self.client.ask(case)
                if "latency_ms" not in response:
                    response["latency_ms"] = int((time.perf_counter() - started) * 1000)
                results.append(evaluate_response(case, response))
            except Exception as exc:
                results.append(
                    EvaluationResult(
                        case=case,
                        passed=False,
                        score=0.0,
                        failure_reasons=(f"evaluation_error: {type(exc).__name__}: {exc}",),
                        latency_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
        return results


def evaluate_response(case: EvaluationCase, response: dict[str, Any]) -> EvaluationResult:
    answer = str(response.get("answer") or "")
    performance = response.get("performance") if isinstance(response.get("performance"), dict) else {}
    agents = _extract_agents(performance)
    tools = _extract_tools(response, performance)
    sources = _extract_sources(response, performance)
    safety_flags = _extract_safety_flags(response)
    tool_execution_records = _extract_tool_records(performance)
    latency_ms = _safe_int(response.get("latency_ms") or performance.get("total_ms"))
    tool_location = str(
        performance.get("tool_execution_location")
        or performance.get("tool_execution_location_actual")
        or ""
    )

    checks = [
        ("agent", *_check_expected("agent", case.expected_agents, agents)),
        ("tool", *_check_expected("tool", case.expected_tools, tools)),
        ("source", *_check_expected("source", case.expected_sources, sources)),
        ("answer", *_check_required_patterns(answer, case.required_answer_patterns)),
        ("answer", *_check_forbidden_patterns(answer, case.forbidden_answer_patterns)),
        ("safety", *_check_expected("safety flag", case.required_safety_flags, safety_flags)),
        ("latency", *_check_latency(latency_ms, case.max_latency_ms)),
    ]
    score = sum(1 for _, passed, _ in checks if passed) / len(checks)
    diagnostic_failures = tuple(reason for _, passed, reason in checks if not passed and reason)
    blocking_failures = tuple(
        reason
        for kind, passed, reason in checks
        if kind in {"answer", "safety"} and not passed and reason
    )
    passed = not blocking_failures and score >= case.minimum_score
    failure_reasons = () if passed else diagnostic_failures
    return EvaluationResult(
        case=case,
        passed=passed,
        score=round(score, 4),
        failure_reasons=failure_reasons,
        answer=answer,
        response=response,
        actual_agents=tuple(agents),
        actual_tools=tuple(tools),
        actual_sources=tuple(sources),
        safety_flags=tuple(safety_flags),
        latency_ms=latency_ms,
        trace_id=str(response.get("trace_id") or ""),
        tool_execution_location=tool_location,
        tool_execution_records=tuple(tool_execution_records),
    )


def _extract_agents(performance: dict[str, Any]) -> list[str]:
    agents = [str(item) for item in performance.get("agents_used", []) if str(item)]
    if agents:
        return _dedupe(agents)
    flow = performance.get("agent_flow", [])
    if not isinstance(flow, list):
        return []
    return _dedupe(
        str(step.get("agent"))
        for step in flow
        if isinstance(step, dict)
        and step.get("agent")
        and str(step.get("agent")) != "SupervisorAgent"
    )


def _extract_tools(response: dict[str, Any], performance: dict[str, Any]) -> list[str]:
    tools = [str(item) for item in response.get("tools_used", []) if str(item)]
    flow = performance.get("agent_flow", [])
    if isinstance(flow, list):
        tools.extend(
            str(step.get("tool"))
            for step in flow
            if isinstance(step, dict) and step.get("tool")
        )
    records = _extract_tool_records(performance)
    tools.extend(str(record.get("tool")) for record in records if record.get("tool"))
    return _dedupe(tools)


def _extract_sources(response: dict[str, Any], performance: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in response.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        values.extend(_source_values_from_mapping(source))
    source_keys = performance.get("source_document_keys") or []
    if isinstance(source_keys, list):
        values.extend(str(item) for item in source_keys)
    values.extend(_source_values_from_performance(performance))
    return _dedupe(item for item in values if item)


def _source_values_from_performance(performance: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for report in performance.get("specialist_reports", []) or []:
        if not isinstance(report, dict):
            continue
        values.extend(_source_values_from_mapping(report))
        values.extend(_source_values_from_mapping(report.get("evidence")))
        values.extend(_source_values_from_mapping(report.get("answer_fragment")))
        values.extend(_source_values_from_mapping(report.get("tool_context")))
    for step in performance.get("agent_flow", []) or []:
        if isinstance(step, dict):
            values.extend(_source_values_from_mapping(step))
    return values


def _source_values_from_mapping(value: Any) -> list[str]:
    source_keys = {
        "_key",
        "domain",
        "document_type",
        "filename",
        "key",
        "kind",
        "lookup_uri",
        "source_filename",
        "source_table",
        "table_key",
        "table_name",
        "title",
        "uri",
    }
    values: list[str] = []
    for item in _iter_source_payloads(value):
        if isinstance(item, dict):
            for key, nested_value in item.items():
                if key in source_keys:
                    values.append(str(nested_value))
                if key in {"metadata", "governance", "row", "rows", "documents", "selected_table_assets", "matched_table_sources"}:
                    values.extend(_source_values_from_mapping(nested_value))
        elif isinstance(item, str):
            values.append(item)
    return values


def _iter_source_payloads(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            if isinstance(nested, (dict, list, tuple)):
                yield from _iter_source_payloads(nested)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_source_payloads(item)
    elif isinstance(value, str):
        for parsed in _json_objects_from_text(value):
            yield from _iter_source_payloads(parsed)


def _json_objects_from_text(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    for match in re.finditer(r"[\[{]", text):
        try:
            parsed, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        objects.append(parsed)
    return objects


def _extract_safety_flags(response: dict[str, Any]) -> list[str]:
    safety = response.get("safety") if isinstance(response.get("safety"), dict) else {}
    flags = safety.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    values = [str(flag) for flag in flags if str(flag)]
    if safety.get("escalation_required"):
        values.append("escalation_required")
    risk = str(safety.get("risk_level") or "")
    if risk:
        values.append(f"risk_level:{risk}")
    return _dedupe(values)


def _extract_tool_records(performance: dict[str, Any]) -> list[dict[str, Any]]:
    records = performance.get("tool_execution_records") or []
    if not isinstance(records, list):
        return []
    return [dict(record) for record in records if isinstance(record, dict)]


def _check_expected(label: str, expected: tuple[str, ...], actual: list[str]) -> tuple[bool, str]:
    if not expected:
        return True, ""
    missing = [item for item in expected if not _contains(actual, item)]
    if not missing:
        return True, ""
    return False, f"Missing expected {label}(s): {', '.join(missing)}. Actual: {', '.join(actual) or 'none'}"


def _check_required_patterns(answer: str, patterns: tuple[str, ...]) -> tuple[bool, str]:
    missing = [pattern for pattern in patterns if not re.search(pattern, answer, flags=re.IGNORECASE | re.MULTILINE)]
    if not missing:
        return True, ""
    return False, f"Missing required answer pattern(s): {', '.join(missing)}"


def _check_forbidden_patterns(answer: str, patterns: tuple[str, ...]) -> tuple[bool, str]:
    found = [pattern for pattern in patterns if re.search(pattern, answer, flags=re.IGNORECASE | re.MULTILINE)]
    if not found:
        return True, ""
    return False, f"Found forbidden answer pattern(s): {', '.join(found)}"


def _check_latency(latency_ms: int, max_latency_ms: int) -> tuple[bool, str]:
    if not max_latency_ms or latency_ms <= max_latency_ms:
        return True, ""
    return False, f"Latency {latency_ms}ms exceeded max {max_latency_ms}ms"


def _contains(values: list[str], needle: str) -> bool:
    expected = needle.lower()
    return any(expected in str(value).lower() for value in values)


def _dedupe(values) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0
