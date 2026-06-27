from __future__ import annotations

from dataclasses import dataclass

from ..deterministic_lookup import DeterministicLookupService
from ..healthcare import HealthcareAccessControl, HealthcareSafetyGuard, HealthcareUserContext
from ..retrieval import RetrievalService
from ..storage import DocumentStore
from .base import AgentTool, build_agent_tools
from .healthcare import build_healthcare_agent_tools


@dataclass(frozen=True)
class LocalToolRegistryContext:
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
