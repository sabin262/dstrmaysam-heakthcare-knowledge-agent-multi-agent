import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from backend.app.config import AppSettings
from backend.app.healthcare import HealthcareAccessControl, HealthcareSafetyGuard, HealthcareUserContext
from backend.app.storage import DocumentStore
from backend.app.tooling import LocalToolRegistryContext, build_tool_registry
from backend.app.tooling.base import AgentTool
from backend.app.tooling.mcp import McpToolClientConfig, McpToolRequestContext, build_mcp_tool_registry


class EmptyRetrieval:
    def search(self, query: str, top_k: int = 5, document_keys=None):
        return []


class EmptyDocuments:
    def list_documents(self):
        return []

    def lookup_table(self, query: str, limit: int = 10):
        return []


def settings(**overrides):
    app_settings = AppSettings(
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
    return replace(app_settings, **overrides)


class ToolRegistryTests(unittest.TestCase):
    def test_local_registry_executes_in_process_tools_by_default(self):
        registry = build_tool_registry(
            LocalToolRegistryContext(
                settings=settings(),
                retrieval=EmptyRetrieval(),
                documents=EmptyDocuments(),
                user=HealthcareUserContext(user_id="user", roles=("staff",)),
                access=HealthcareAccessControl(),
                safety=HealthcareSafetyGuard(),
            )
        )

        tools = {tool.name: tool for tool in registry}

        self.assertIn("rag_search", tools)
        self.assertEqual(tools["rag_search"].run("anything"), "No relevant document chunks found.")

    def test_mcp_registry_preserves_contract_and_forwards_payload(self):
        calls = []

        async def fake_call(config, tool_name, payload):
            calls.append({"config": config, "tool_name": tool_name, "payload": payload})
            return json.dumps({"ok": True, "tool": tool_name})

        local_tools = [AgentTool(name="rag_search", description="Search docs", run=lambda query: "local")]
        user = HealthcareUserContext(user_id="user", roles=("staff",), departments=("ops",))

        with patch("backend.app.tooling.mcp._call_fastmcp_tool", side_effect=fake_call):
            registry = build_mcp_tool_registry(
                local_tools,
                config=McpToolClientConfig(server_url="http://mcp.example/mcp", timeout_seconds=5),
                context=McpToolRequestContext(user=user, app_context={"settings": {"app_env": "test"}}),
            )
            output = registry[0].run("find iot policy")

        self.assertEqual(registry[0].name, "rag_search")
        self.assertEqual(registry[0].description, "Search docs")
        self.assertEqual(json.loads(output), {"ok": True, "tool": "rag_search"})
        self.assertEqual(calls[0]["tool_name"], "rag_search")
        self.assertEqual(calls[0]["config"].server_url, "http://mcp.example/mcp")
        self.assertEqual(calls[0]["payload"]["query"], "find iot policy")
        self.assertEqual(calls[0]["payload"]["user"]["roles"], ["staff"])
        self.assertEqual(calls[0]["payload"]["app_context"], {"settings": {"app_env": "test"}})


if __name__ == "__main__":
    unittest.main()
