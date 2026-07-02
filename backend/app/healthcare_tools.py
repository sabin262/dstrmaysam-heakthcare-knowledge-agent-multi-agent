from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from .config import AppSettings
from .deterministic_lookup import DeterministicLookupService, detect_csv_table_mapping
from .healthcare import HealthcareAccessControl, HealthcareSafetyGuard, HealthcareUserContext
from .retrieval import RetrievalService
from .storage import DocumentStore
from .tool_execution import ToolExecutionRouter
from .tools import AgentTool

_package_src = Path(__file__).resolve().parents[1] / "packages" / "healthcare_tools_core" / "src"
if _package_src.exists() and str(_package_src) not in sys.path:
    sys.path.insert(0, str(_package_src))

from healthcare_tools_core import HealthcareToolExecutor  # noqa: E402


def _deterministic_table_assets(
    *,
    documents: DocumentStore,
    user: HealthcareUserContext,
    access: HealthcareAccessControl,
) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    try:
        records = access.filter_documents(user, documents.list_documents())
    except Exception:
        return assets
    for record in records:
        metadata = record.metadata
        asset_source = str(metadata.get("asset_source") or "")
        if asset_source not in {"postgres_table_lookup", "postgres_uploaded_lookup"}:
            continue
        columns = [str(column) for column in metadata.get("columns") or [] if str(column).strip()]
        semantic_terms = [str(term) for term in metadata.get("semantic_terms") or [] if str(term).strip()]
        sample_values = [str(value) for value in metadata.get("sample_values") or [] if str(value).strip()]
        categorical_values = metadata.get("categorical_values") or {}
        source_filename = str(metadata.get("source_filename") or record.title or record.key.rsplit("/", 1)[-1])
        table_name = str(metadata.get("source_table") or "")
        table_key = str(metadata.get("source_table_key") or "")
        if table_name == "uploaded_lookup_rows" or not table_name:
            mapping = detect_csv_table_mapping(source_filename, columns) or {}
            table_name = str(mapping.get("table_name") or table_name)
            table_key = str(mapping.get("table_key") or table_key)
        assets.append(
            {
                "table_name": table_name,
                "table_key": table_key,
                "filename": source_filename if asset_source == "postgres_uploaded_lookup" else table_name,
                "title": record.title,
                "columns": columns,
                "semantic_terms": semantic_terms,
                "categorical_values": categorical_values,
                "sample_values": sample_values,
                "row_count": int(metadata.get("row_count") or 0),
            }
        )
    return assets[:20]


def _deterministic_tool_description(table_assets: list[dict[str, Any]]) -> str:
    base = (
        "Exact Postgres lookup for patient details, contact information, doctor information, "
        "department directory data, appointments, wards, formulary facts, staff rota availability, "
        "equipment assets, finance, compliance, training, and table-backed uploaded CSV data. "
        "Use this when the user asks for exact structured values, multiple known values to look up, "
        "counts/totals, inventory or equipment availability, short entity facts such as medicine names, "
        "or table-like data that can answer the question without document interpretation."
    )
    if not table_assets:
        return base
    asset_lines = []
    for asset in table_assets[:8]:
        columns = ", ".join(asset.get("columns") or [])
        semantic_terms = ", ".join((asset.get("semantic_terms") or [])[:12])
        asset_lines.append(
            f"{asset.get('table_name')} ({asset.get('row_count', 0)} rows; "
            f"columns: {columns or 'unknown'}; terms: {semantic_terms or 'unknown'})"
        )
    return base + " Available table lookup assets: " + " | ".join(asset_lines)


def build_healthcare_agent_tools(
    *,
    retrieval: RetrievalService,
    documents: DocumentStore,
    user: HealthcareUserContext,
    access: HealthcareAccessControl,
    safety: HealthcareSafetyGuard,
    deterministic_lookup: DeterministicLookupService | None = None,
    settings: AppSettings | None = None,
) -> list[AgentTool]:
    router = ToolExecutionRouter(settings, user)
    deterministic_table_assets = _deterministic_table_assets(
        documents=documents,
        user=user,
        access=access,
    )
    executor = HealthcareToolExecutor(
        settings,
        retrieval=retrieval,
        documents=documents,
        deterministic_lookup=deterministic_lookup,
    )

    def routed(name: str, *, extra_payload: dict[str, Any] | None = None):
        def run(query: str) -> str:
            return router.run(
                name,
                query,
                lambda value: executor.execute_tool(name, value, user_context=user, extra=extra_payload or {}),
                extra_payload=extra_payload,
            )

        return run

    return [
        AgentTool(
            name="document_search",
            description="Semantic search over approved healthcare documents.",
            run=routed("document_search"),
        ),
        AgentTool(
            name="policy_search",
            description="Focused retrieval over approved clinical/admin policies, SOPs, pathways, and guidelines.",
            run=routed("policy_search"),
        ),
        AgentTool(
            name="catalogue_search",
            description="List and filter approved healthcare document inventory and metadata.",
            run=routed("catalogue_search"),
        ),
        AgentTool(
            name="calendar_rota_lookup",
            description=(
                "Lookup clinics, training, and general rota schedules from approved structured sources. "
                "For staff availability, doctors, nurses, or on-call questions, prefer postgres_deterministic_lookup."
            ),
            run=routed("calendar_rota_lookup", extra_payload={"table_assets": deterministic_table_assets}),
        ),
        AgentTool(
            name="formulary_table_lookup",
            description="Lookup restricted medicines, formulary rows, approval rules, codes, and structured facts.",
            run=routed("formulary_table_lookup", extra_payload={"table_assets": deterministic_table_assets}),
        ),
        AgentTool(
            name="postgres_deterministic_lookup",
            description=_deterministic_tool_description(deterministic_table_assets),
            run=routed("postgres_deterministic_lookup", extra_payload={"table_assets": deterministic_table_assets}),
        ),
        AgentTool(
            name="safety_guard",
            description="Detect clinical risk, missing sources, PHI exposure, or escalation needs.",
            run=routed("safety_guard"),
        ),
    ]
