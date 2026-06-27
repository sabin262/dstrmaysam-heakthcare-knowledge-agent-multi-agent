from __future__ import annotations

from dataclasses import dataclass

from ..config import AppSettings
from ..deterministic_lookup import DeterministicLookupService
from ..healthcare import HealthcareAccessControl, HealthcareSafetyGuard, HealthcareUserContext
from ..retrieval import RetrievalService
from ..storage import DocumentStore
from .base import AgentTool, build_agent_tools
from .healthcare import build_healthcare_agent_tools
from .mcp import McpToolClientConfig, McpToolRequestContext, build_mcp_tool_registry


@dataclass(frozen=True)
class LocalToolRegistryContext:
    settings: AppSettings
    retrieval: RetrievalService
    documents: DocumentStore
    user: HealthcareUserContext
    access: HealthcareAccessControl
    safety: HealthcareSafetyGuard
    deterministic_lookup: DeterministicLookupService | None = None


def build_local_tool_registry(context: LocalToolRegistryContext) -> list[AgentTool]:
    """Build all in-process tools used by the multi-agent graph."""
    core_tools = build_agent_tools(context.retrieval, context.documents)
    healthcare_tools = build_healthcare_agent_tools(
        retrieval=context.retrieval,
        documents=context.documents,
        user=context.user,
        access=context.access,
        safety=context.safety,
        deterministic_lookup=context.deterministic_lookup,
    )
    return core_tools + healthcare_tools


def build_tool_registry(context: LocalToolRegistryContext) -> list[AgentTool]:
    local_tools = build_local_tool_registry(context)
    if context.settings.tool_execution_backend != "mcp":
        return local_tools
    return build_mcp_tool_registry(
        local_tools,
        config=McpToolClientConfig(
            server_url=context.settings.mcp_tool_server_url,
            timeout_seconds=context.settings.mcp_tool_timeout_seconds,
        ),
        context=McpToolRequestContext(
            user=context.user,
            app_context={
                "settings": context.settings.public_summary(),
                "tool_execution_backend": context.settings.tool_execution_backend,
            },
        ),
    )
