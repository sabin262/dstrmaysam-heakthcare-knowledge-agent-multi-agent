import json
import unittest

from backend.app import deterministic_lookup as backend_lookup
from backend.app.agent import (
    _deterministic_guard_queries,
    _format_deterministic_lookup_payload,
    _normalize_chat_execution_mode,
)
from backend.app.config import AppSettings
from backend.app.healthcare import HealthcareAccessControl, HealthcareUserContext
from backend.app.healthcare_tools import build_healthcare_agent_tools
from backend.app.models import ChatRequest
from backend.app.secrets import StaticSecretProvider
from backend.app.storage import DocumentRecord
from backend.app.tool_execution import ToolExecutionRouter
from healthcare_tools_core.deterministic_lookup import DeterministicLookupService as CoreDeterministicLookupService


def settings(**overrides) -> AppSettings:
    values = dict(
        app_env="test",
        aws_region="eu-west-2",
        secrets_stage="test",
        app_secret_name="/test/app",
        azure_openai_secret_name="/test/azure",
        langfuse_secret_name="/test/langfuse",
        s3_bucket="bucket",
        s3_raw_prefix="raw/",
        s3_manifest_key="manifest.json",
        opensearch_endpoint="",
        opensearch_index="idx",
        dynamodb_chat_table="table",
        chat_history_backend="memory",
        cors_origins=(),
        prompt_label="dev",
        max_history_chars=1000,
    )
    values.update(overrides)
    return AppSettings(**values)


class FakeRetrieval:
    def __init__(self, hits=None):
        self.hits = list(hits or [])

    def search(self, query):
        return list(self.hits)


class FakeDocuments:
    def __init__(self, records=None):
        self.records = list(records or [])

    def list_documents(self):
        return list(self.records)


class FakeSafety:
    def assess(self, query):
        class Assessment:
            def as_dict(self):
                return {"risk_level": "low", "allow_answer": True}

        return Assessment()


class FakeLookupResult:
    def __init__(self, payload):
        self.payload = payload

    def to_json(self):
        return json.dumps(self.payload)


class FakeDeterministicLookup:
    def __init__(self):
        self.calls = []

    def lookup(self, query, user, limit=10, table_assets=None, csv_assets=None):
        self.calls.append(
            {
                "query": query,
                "user": user.user_id,
                "limit": limit,
                "table_assets": list(table_assets or []),
                "csv_assets": list(csv_assets or []),
            }
        )
        return FakeLookupResult({"category": "test", "rows": [{"row": {"name": "A"}}], "message": "ok"})


class PrePushCriticalTests(unittest.TestCase):
    def test_legacy_chat_execution_modes_are_normalized_to_supervisor(self):
        self.assertEqual(_normalize_chat_execution_mode("agent_only"), "supervisor")
        self.assertEqual(_normalize_chat_execution_mode("deterministic_agent"), "supervisor")

    def test_chat_request_still_accepts_legacy_execution_mode_field(self):
        request = ChatRequest(query="who is on call", execution_mode="agent_only")
        self.assertEqual(request.execution_mode, "agent_only")

    def test_backend_deterministic_lookup_uses_shared_core_package(self):
        self.assertIs(backend_lookup.DeterministicLookupService, CoreDeterministicLookupService)
        self.assertTrue(hasattr(backend_lookup, "_requested_rota_dates"))

    def test_deterministic_guard_splits_multipart_structured_queries(self):
        queries = _deterministic_guard_queries(
            "who is on call tomorrow? Does John Spencer have appointments?"
        )
        self.assertEqual(len(queries), 2)
        self.assertIn("who is on call tomorrow", queries[0].lower())
        self.assertIn("john spencer", queries[1].lower())

    def test_deterministic_count_format_does_not_invent_extra_sources(self):
        answer = _format_deterministic_lookup_payload(
            "how many ventilators are available",
            {
                "lookup_plan": {
                    "aggregate_result": {
                        "type": "count",
                        "matching_rows": 2,
                        "source_tables": ["equipment_assets"],
                    }
                },
                "rows": [
                    {"row": {"equipment_type": "Ventilator", "location": "ICU", "status": "Available"}},
                    {"row": {"equipment_type": "Ventilator", "location": "Respiratory", "status": "Available"}},
                ],
            },
        )
        self.assertIn("Total: 2 matching row(s) in equipment_assets.", answer)
        self.assertIn("Ventilator", answer)
        self.assertNotIn("Defibrillator", answer)

    def test_tool_router_local_mode_calls_local_function_without_mcp(self):
        router = ToolExecutionRouter(settings(tool_execution_mode="local"), HealthcareUserContext("alice"))
        result = router.run("postgres_deterministic_lookup", "query", lambda query: f"local:{query}")
        self.assertEqual(result, "local:query")

    def test_tool_router_mcp_failure_can_fallback_to_local(self):
        router = ToolExecutionRouter(
            settings(tool_execution_mode="mcp", mcp_tool_fallback_to_local=True),
            HealthcareUserContext("alice"),
        )

        class FailingClient:
            def call_project_tool(self, tool_name, payload):
                raise RuntimeError("offline")

        router._client = FailingClient()
        result = router.run("postgres_deterministic_lookup", "query", lambda query: f"local:{query}")
        self.assertEqual(result, "local:query")

    def test_healthcare_tool_builder_passes_table_metadata_to_deterministic_lookup(self):
        record = DocumentRecord(
            key="postgres://table/staff_schedule",
            title="Schedule table",
            uri="postgres://table/staff_schedule",
            content_type="application/vnd.postgresql.table+json",
            metadata={
                "asset_source": "postgres_table_lookup",
                "source_table": "staff_schedule",
                "source_table_key": "schedule",
                "columns": ["staff_name", "department_name", "on_call"],
                "semantic_terms": ["rota", "on call"],
                "allowed_roles": ["staff"],
                "row_count": 10,
            },
            chunk_count=0,
        )
        lookup = FakeDeterministicLookup()
        tools = build_healthcare_agent_tools(
            retrieval=FakeRetrieval(),
            documents=FakeDocuments([record]),
            user=HealthcareUserContext("alice", roles=("staff",)),
            access=HealthcareAccessControl(),
            safety=FakeSafety(),
            deterministic_lookup=lookup,
            settings=settings(tool_execution_mode="local"),
        )
        tool = next(item for item in tools if item.name == "postgres_deterministic_lookup")
        tool.run("who is on call")
        self.assertEqual(lookup.calls[-1]["limit"], 50)
        self.assertEqual(lookup.calls[-1]["table_assets"][0]["table_name"], "staff_schedule")

    def test_static_secret_provider_loads_tool_execution_from_app_secret(self):
        provider = StaticSecretProvider(
            settings(),
            {
                "/test/app": {
                    "tool_execution_mode": "mcp",
                    "mcp_server_url": "http://mcp.local/sse",
                    "mcp_project_id": "project",
                    "mcp_tool_timeout_seconds": 7,
                    "mcp_tool_fallback_to_local": True,
                }
            },
        )
        secrets = provider.load_tool_execution()
        self.assertEqual(secrets.tool_execution_mode, "mcp")
        self.assertEqual(secrets.mcp_server_url, "http://mcp.local/sse")
        self.assertTrue(secrets.mcp_tool_fallback_to_local)

    def test_policy_metadata_is_filtered_before_generic_document_search_answering(self):
        policy_hit = type(
            "Hit",
            (),
            {
                "title": "Data Retention Policy",
                "uri": "policy://retention",
                "text": "Patient data is retained under the retention schedule.",
                "score": 1.0,
                "metadata": {"domain": "clinical_policy", "document_type": "policy", "allowed_roles": ["staff"]},
            },
        )()
        tools = build_healthcare_agent_tools(
            retrieval=FakeRetrieval([policy_hit]),
            documents=FakeDocuments(),
            user=HealthcareUserContext("alice", roles=("staff",)),
            access=HealthcareAccessControl(),
            safety=FakeSafety(),
            deterministic_lookup=FakeDeterministicLookup(),
            settings=settings(tool_execution_mode="local"),
        )
        tool = next(item for item in tools if item.name == "policy_search")
        answer = tool.run("how long is patient data stored")
        self.assertIn("Data Retention Policy", answer)
        self.assertIn("Patient data is retained", answer)


if __name__ == "__main__":
    unittest.main()
