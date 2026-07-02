from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable

from .config import AppSettings
from .retrieval import RetrievalService
from .storage import DocumentStore
from .tool_execution import ToolExecutionRouter

_package_src = Path(__file__).resolve().parents[1] / "packages" / "healthcare_tools_core" / "src"
if _package_src.exists() and str(_package_src) not in sys.path:
    sys.path.insert(0, str(_package_src))

from healthcare_tools_core import (  # noqa: E402
    HealthcareToolExecutor,
    catalog_query_terms,
    document_catalog_payload,
    document_matches_catalog_query,
    format_retrieval_hits,
)


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    run: Callable[[str], str]


def build_agent_tools(
    retrieval: RetrievalService,
    documents: DocumentStore,
    settings: AppSettings | None = None,
) -> list[AgentTool]:
    router = ToolExecutionRouter(settings)
    executor = HealthcareToolExecutor(
        settings,
        retrieval=retrieval,
        documents=documents,
    )

    def run_shared(tool_name: str, query: str) -> str:
        return executor.execute_tool(tool_name, query)

    def routed(name: str) -> Callable[[str], str]:
        def run(query: str) -> str:
            return router.run(name, query, lambda value: run_shared(name, value))

        return run

    return [
        AgentTool(
            name="rag_search",
            description="Semantic RAG search over indexed knowledge documents with citations.",
            run=routed("rag_search"),
        ),
        AgentTool(
            name="document_catalog",
            description="List and filter available S3 knowledge documents by metadata.",
            run=routed("document_catalog"),
        ),
        AgentTool(
            name="table_lookup",
            description="Find exact values from controlled Postgres lookup tables.",
            run=routed("table_lookup"),
        ),
    ]
