import io
import json
import urllib.error

from backend.system_evals.dataset import load_bundled_dataset
from backend.system_evals.evaluator import EvaluationRunner, HttpChatClient, StaticChatClient, evaluate_response
from backend.system_evals.reporting import markdown_report
from backend.system_evals.schema import summarize_results


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_bundled_system_golden_dataset_has_required_coverage():
    cases = load_bundled_dataset("system_golden_v1")

    assert len(cases) >= 40
    categories = {case.category for case in cases}
    assert {
        "deterministic",
        "policy",
        "catalog",
        "rag",
        "safety",
        "multipart",
    }.issubset(categories)
    assert all(case.id and case.query for case in cases)


def test_bundled_system_stress_dataset_has_100_cases_and_defaults():
    cases = load_bundled_dataset("system_stress_v1")

    assert len(cases) == 100
    categories = {case.category for case in cases}
    assert {
        "deterministic",
        "policy",
        "catalog",
        "rag",
        "safety",
        "multipart",
        "no_evidence",
    }.issubset(categories)
    assert all(case.minimum_score == 0.72 for case in cases)
    assert all(case.max_latency_ms == 60000 for case in cases)
    assert all(case.expected_agents and case.expected_tools for case in cases)


def test_evaluate_response_passes_when_expected_contract_matches():
    case = load_bundled_dataset("system_golden_v1")[0]
    response = {
        "answer": "On call staff are listed by department, role and contact.",
        "tools_used": ["postgres_deterministic_lookup"],
        "sources": [{"title": "staff_schedule", "uri": "postgres://table/staff_schedule", "metadata": {"source_table": "staff_schedule"}}],
        "latency_ms": 100,
        "trace_id": "trace-1",
        "safety": {"risk_level": "low", "flags": []},
        "performance": {
            "agents_used": ["DeterministicLookupAgent", "SynthesisAgent"],
            "tool_execution_location": "Backend local tools",
            "tool_execution_records": [{"tool": "postgres_deterministic_lookup", "status": "local_only"}],
        },
    }

    result = evaluate_response(case, response)

    assert result.passed
    assert result.score == 1.0
    assert "DeterministicLookupAgent" in result.actual_agents
    assert "postgres_deterministic_lookup" in result.actual_tools


def test_evaluate_response_reports_readable_failures():
    case = load_bundled_dataset("system_golden_v1")[0]
    response = {
        "answer": "No idea.",
        "tools_used": ["document_search"],
        "sources": [],
        "latency_ms": 999999,
        "safety": {"flags": []},
        "performance": {"agents_used": ["RAGAgent"]},
    }

    result = evaluate_response(case, response)

    assert not result.passed
    assert any("Missing expected agent" in reason for reason in result.failure_reasons)
    assert any("Missing expected tool" in reason for reason in result.failure_reasons)
    assert any("Latency" in reason for reason in result.failure_reasons)


def test_evaluate_response_extracts_sources_from_specialist_tool_context():
    case = load_bundled_dataset("system_golden_v1")[0]
    response = {
        "answer": "On-call staff are listed by department, role and contact.",
        "tools_used": ["postgres_deterministic_lookup"],
        "sources": [],
        "latency_ms": 100,
        "safety": {"flags": []},
        "performance": {
            "agents_used": ["DeterministicLookupAgent", "SynthesisAgent"],
            "specialist_reports": [
                {
                    "agent": "DeterministicLookupAgent",
                    "tool_context": (
                        'postgres_deterministic_lookup results:\n'
                        '{"matched_table_sources":["staff_schedule"],'
                        '"rows":[{"source_table":"staff_schedule","row":{"staff_name":"Lucy Hall"}}]}'
                    ),
                }
            ],
        },
    }

    result = evaluate_response(case, response)

    assert result.passed
    assert "staff_schedule" in result.actual_sources


def test_runner_aggregates_static_client_results():
    cases = load_bundled_dataset("system_golden_v1")[:2]
    responses = {
        cases[0].id: {
            "answer": "On call staff are listed by department, role and contact.",
            "tools_used": ["postgres_deterministic_lookup"],
            "sources": [{"title": "staff_schedule", "uri": "postgres://table/staff_schedule", "metadata": {"source_table": "staff_schedule"}}],
            "latency_ms": 100,
            "safety": {"flags": []},
            "performance": {"agents_used": ["DeterministicLookupAgent"]},
        },
        cases[1].id: {
            "answer": "Radiology has no matching on-call staff tomorrow.",
            "tools_used": ["postgres_deterministic_lookup"],
            "sources": [{"title": "staff_schedule", "uri": "postgres://table/staff_schedule", "metadata": {"source_table": "staff_schedule"}}],
            "latency_ms": 100,
            "safety": {"flags": []},
            "performance": {"agents_used": ["DeterministicLookupAgent"]},
        },
    }

    results = EvaluationRunner(StaticChatClient(responses)).run(cases)
    summary = summarize_results("system_golden_v1", results)

    assert summary.total_cases == 2
    assert summary.passed_cases == 2
    assert summary.routing_accuracy == 1.0
    assert summary.tool_accuracy == 1.0


def test_markdown_report_contains_summary_and_case_details():
    case = load_bundled_dataset("system_golden_v1")[0]
    result = evaluate_response(
        case,
        {
            "answer": "On call staff are listed by department, role and contact.",
            "tools_used": ["postgres_deterministic_lookup"],
            "sources": [{"title": "staff_schedule", "uri": "postgres://table/staff_schedule", "metadata": {"source_table": "staff_schedule"}}],
            "latency_ms": 100,
            "safety": {"flags": []},
            "performance": {"agents_used": ["DeterministicLookupAgent"]},
        },
    )
    summary = summarize_results("system_golden_v1", [result])

    report = markdown_report(run_id="run-1", summary=summary, results=[result])

    assert "# System Evaluation Report: run-1" in report
    assert "det_on_call_today" in report
    assert "On call staff" in report


def test_http_chat_client_retries_transient_chat_http_errors(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("/auth/login"):
            return FakeHttpResponse({"access_token": "token"})
        if len([url for url in calls if url.endswith("/chat")]) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b"rate limited"),
            )
        return FakeHttpResponse(
            {
                "answer": "ok",
                "tools_used": [],
                "sources": [],
                "performance": {},
            }
        )

    monkeypatch.setattr("backend.system_evals.evaluator.urllib.request.urlopen", fake_urlopen)
    client = HttpChatClient(
        base_url="http://backend",
        username="admin",
        password="password",
        retry_attempts=2,
        retry_initial_seconds=0,
        retry_max_seconds=0,
    )

    response = client.ask(load_bundled_dataset("system_golden_v1")[0])

    assert response["answer"] == "ok"
    assert response["performance"]["system_eval_http_retry_count"] == 1
    assert len([url for url in calls if url.endswith("/chat")]) == 2
