from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..config import AppSettings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StoredEvaluationRun:
    run_id: str
    dataset_id: str
    dataset_version: str
    environment: str
    tool_mode: str
    status: str
    started_at: str
    completed_at: str | None
    requested_by: str
    semantic_judge_enabled: bool
    category_filter: list[str]
    user_filter: str
    summary: dict[str, Any]
    report_markdown: str


class PostgresEvaluationRepository:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._ensure_schema()

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for system evaluation storage") from exc

        return psycopg.connect(
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            dbname=self.settings.postgres_db,
            user=self.settings.postgres_user,
            password=self.settings.postgres_password,
            sslmode=self.settings.postgres_sslmode,
            row_factory=dict_row,
            connect_timeout=3,
        )

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(EVAL_RUNS_SCHEMA)
                cur.execute(EVAL_CASE_RESULTS_SCHEMA)
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_system_eval_runs_started_at
                    ON system_eval_runs (started_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_system_eval_case_results_run
                    ON system_eval_case_results (run_id, case_id)
                    """
                )
            conn.commit()

    def create_run(
        self,
        *,
        dataset_id: str,
        dataset_version: str,
        environment: str,
        tool_mode: str,
        requested_by: str,
        semantic_judge_enabled: bool,
        category_filter: list[str],
        user_filter: str,
    ) -> str:
        run_id = uuid.uuid4().hex
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO system_eval_runs (
                        run_id, dataset_id, dataset_version, environment, tool_mode,
                        status, started_at, requested_by, semantic_judge_enabled,
                        category_filter, user_filter, summary, report_markdown
                    )
                    VALUES (%s, %s, %s, %s, %s, 'running', %s, %s, %s, %s::jsonb, %s, '{}'::jsonb, '')
                    """,
                    (
                        run_id,
                        dataset_id,
                        dataset_version,
                        environment,
                        tool_mode,
                        utc_now_iso(),
                        requested_by,
                        semantic_judge_enabled,
                        json.dumps(category_filter),
                        user_filter,
                    ),
                )
            conn.commit()
        return run_id

    def complete_run(
        self,
        *,
        run_id: str,
        status: str,
        summary: dict[str, Any],
        report_markdown: str,
        results: list[dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE system_eval_runs
                    SET status = %s,
                        completed_at = %s,
                        summary = %s::jsonb,
                        report_markdown = %s
                    WHERE run_id = %s
                    """,
                    (status, utc_now_iso(), json.dumps(summary), report_markdown, run_id),
                )
                for result in results:
                    cur.execute(
                        """
                        INSERT INTO system_eval_case_results (
                            run_id, case_id, category, query, expected, actual,
                            answer, sources, tools, agents, safety, score, passed,
                            failure_reasons, latency_ms, trace_id, tool_execution_location,
                            tool_execution_records, raw_response
                        )
                        VALUES (
                            %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                            %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s,
                            %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb
                        )
                        ON CONFLICT (run_id, case_id) DO UPDATE
                        SET category = EXCLUDED.category,
                            query = EXCLUDED.query,
                            expected = EXCLUDED.expected,
                            actual = EXCLUDED.actual,
                            answer = EXCLUDED.answer,
                            sources = EXCLUDED.sources,
                            tools = EXCLUDED.tools,
                            agents = EXCLUDED.agents,
                            safety = EXCLUDED.safety,
                            score = EXCLUDED.score,
                            passed = EXCLUDED.passed,
                            failure_reasons = EXCLUDED.failure_reasons,
                            latency_ms = EXCLUDED.latency_ms,
                            trace_id = EXCLUDED.trace_id,
                            tool_execution_location = EXCLUDED.tool_execution_location,
                            tool_execution_records = EXCLUDED.tool_execution_records,
                            raw_response = EXCLUDED.raw_response
                        """,
                        _case_result_params(run_id, result),
                    )
            conn.commit()

    def update_run_progress(
        self,
        *,
        run_id: str,
        status: str = "running",
        summary: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE system_eval_runs
                    SET status = %s,
                        summary = %s::jsonb
                    WHERE run_id = %s
                    """,
                    (status, json.dumps(summary), run_id),
                )
            conn.commit()

    def store_case_result(self, *, run_id: str, result: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO system_eval_case_results (
                        run_id, case_id, category, query, expected, actual,
                        answer, sources, tools, agents, safety, score, passed,
                        failure_reasons, latency_ms, trace_id, tool_execution_location,
                        tool_execution_records, raw_response
                    )
                    VALUES (
                        %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                        %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s,
                        %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb
                    )
                    ON CONFLICT (run_id, case_id) DO UPDATE
                    SET category = EXCLUDED.category,
                        query = EXCLUDED.query,
                        expected = EXCLUDED.expected,
                        actual = EXCLUDED.actual,
                        answer = EXCLUDED.answer,
                        sources = EXCLUDED.sources,
                        tools = EXCLUDED.tools,
                        agents = EXCLUDED.agents,
                        safety = EXCLUDED.safety,
                        score = EXCLUDED.score,
                        passed = EXCLUDED.passed,
                        failure_reasons = EXCLUDED.failure_reasons,
                        latency_ms = EXCLUDED.latency_ms,
                        trace_id = EXCLUDED.trace_id,
                        tool_execution_location = EXCLUDED.tool_execution_location,
                        tool_execution_records = EXCLUDED.tool_execution_records,
                        raw_response = EXCLUDED.raw_response
                    """,
                    _case_result_params(run_id, result),
                )
            conn.commit()

    def fail_run(self, run_id: str, error: str) -> None:
        summary = {"error": error, "total_cases": 0, "passed_cases": 0, "failed_cases": 0, "pass_rate": 0}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE system_eval_runs
                    SET status = 'failed',
                        completed_at = %s,
                        summary = %s::jsonb,
                        report_markdown = %s
                    WHERE run_id = %s
                    """,
                    (utc_now_iso(), json.dumps(summary), f"# Evaluation failed\n\n{error}", run_id),
                )
            conn.commit()

    def list_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, dataset_id, dataset_version, environment, tool_mode,
                           status, started_at, completed_at, requested_by,
                           semantic_judge_enabled, category_filter, user_filter, summary
                    FROM system_eval_runs
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = list(cur.fetchall())
        return [_run_row_to_dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, dataset_id, dataset_version, environment, tool_mode,
                           status, started_at, completed_at, requested_by,
                           semantic_judge_enabled, category_filter, user_filter, summary,
                           report_markdown
                    FROM system_eval_runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                run = cur.fetchone()
                if not run:
                    return None
                cur.execute(
                    """
                    SELECT case_id, category, query, expected, actual, answer, sources,
                           tools, agents, safety, score, passed, failure_reasons,
                           latency_ms, trace_id, tool_execution_location,
                           tool_execution_records, raw_response
                    FROM system_eval_case_results
                    WHERE run_id = %s
                    ORDER BY case_id
                    """,
                    (run_id,),
                )
                cases = [_case_row_to_dict(row) for row in cur.fetchall()]
        payload = _run_row_to_dict(run)
        payload["report_markdown"] = run.get("report_markdown") or ""
        payload["cases"] = cases
        return payload

    def get_report(self, run_id: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT report_markdown FROM system_eval_runs WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        if not row:
            return None
        return str(row.get("report_markdown") or "")


EVAL_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_eval_runs (
    run_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    environment TEXT NOT NULL,
    tool_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    requested_by TEXT NOT NULL,
    semantic_judge_enabled BOOLEAN NOT NULL DEFAULT false,
    category_filter JSONB NOT NULL DEFAULT '[]'::jsonb,
    user_filter TEXT NOT NULL DEFAULT '',
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_markdown TEXT NOT NULL DEFAULT ''
)
"""


EVAL_CASE_RESULTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_eval_case_results (
    run_id TEXT NOT NULL REFERENCES system_eval_runs(run_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    category TEXT NOT NULL,
    query TEXT NOT NULL,
    expected JSONB NOT NULL DEFAULT '{}'::jsonb,
    actual JSONB NOT NULL DEFAULT '{}'::jsonb,
    answer TEXT NOT NULL DEFAULT '',
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    tools JSONB NOT NULL DEFAULT '[]'::jsonb,
    agents JSONB NOT NULL DEFAULT '[]'::jsonb,
    safety JSONB NOT NULL DEFAULT '{}'::jsonb,
    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    passed BOOLEAN NOT NULL DEFAULT false,
    failure_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    trace_id TEXT NOT NULL DEFAULT '',
    tool_execution_location TEXT NOT NULL DEFAULT '',
    tool_execution_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (run_id, case_id)
)
"""


def _case_result_params(run_id: str, result: dict[str, Any]) -> tuple[Any, ...]:
    case = result.get("case") if isinstance(result.get("case"), dict) else {}
    response = result.get("response") if isinstance(result.get("response"), dict) else {}
    safety = response.get("safety") if isinstance(response.get("safety"), dict) else {}
    expected = dict(case)
    expected.update(
        {
            "agents": case.get("expected_agents", []),
            "tools": case.get("expected_tools", []),
            "sources": case.get("expected_sources", []),
        }
    )
    actual = {
        "agents": result.get("actual_agents", []),
        "tools": result.get("actual_tools", []),
        "sources": result.get("actual_sources", []),
        "safety_flags": result.get("safety_flags", []),
    }
    return (
        run_id,
        result.get("case_id", ""),
        result.get("category", ""),
        result.get("query", ""),
        json.dumps(expected),
        json.dumps(actual),
        result.get("answer", ""),
        json.dumps(result.get("actual_sources", [])),
        json.dumps(result.get("actual_tools", [])),
        json.dumps(result.get("actual_agents", [])),
        json.dumps(safety),
        float(result.get("score") or 0),
        bool(result.get("passed")),
        json.dumps(result.get("failure_reasons", [])),
        int(result.get("latency_ms") or 0),
        result.get("trace_id", ""),
        result.get("tool_execution_location", ""),
        json.dumps(result.get("tool_execution_records", [])),
        json.dumps(response),
    )


def _run_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row.get("run_id") or ""),
        "dataset_id": str(row.get("dataset_id") or ""),
        "dataset_version": str(row.get("dataset_version") or ""),
        "environment": str(row.get("environment") or ""),
        "tool_mode": str(row.get("tool_mode") or ""),
        "status": str(row.get("status") or ""),
        "started_at": str(row.get("started_at") or ""),
        "completed_at": str(row.get("completed_at") or ""),
        "requested_by": str(row.get("requested_by") or ""),
        "semantic_judge_enabled": bool(row.get("semantic_judge_enabled")),
        "category_filter": _json_value(row.get("category_filter"), []),
        "user_filter": str(row.get("user_filter") or ""),
        "summary": _json_value(row.get("summary"), {}),
    }


def _case_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(row.get("case_id") or ""),
        "category": str(row.get("category") or ""),
        "query": str(row.get("query") or ""),
        "expected": _json_value(row.get("expected"), {}),
        "actual": _json_value(row.get("actual"), {}),
        "answer": str(row.get("answer") or ""),
        "sources": _json_value(row.get("sources"), []),
        "tools": _json_value(row.get("tools"), []),
        "agents": _json_value(row.get("agents"), []),
        "safety": _json_value(row.get("safety"), {}),
        "score": float(row.get("score") or 0),
        "passed": bool(row.get("passed")),
        "failure_reasons": _json_value(row.get("failure_reasons"), []),
        "latency_ms": int(row.get("latency_ms") or 0),
        "trace_id": str(row.get("trace_id") or ""),
        "tool_execution_location": str(row.get("tool_execution_location") or ""),
        "tool_execution_records": _json_value(row.get("tool_execution_records"), []),
        "raw_response": _json_value(row.get("raw_response"), {}),
    }


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value
