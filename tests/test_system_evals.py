from backend.system_evals.dataset import load_bundled_dataset
from backend.system_evals.evaluator import EvaluationRunner, StaticChatClient, evaluate_response
from backend.system_evals.reporting import markdown_report
from backend.system_evals.schema import summarize_results


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
