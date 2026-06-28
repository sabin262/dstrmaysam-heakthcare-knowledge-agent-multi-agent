from __future__ import annotations

import json
from typing import Any

from .config import AppSettings
from .healthcare import (
    HealthcareAccessControl,
    HealthcareSafetyGuard,
    HealthcareUserContext,
    SourceGovernance,
)
from .deterministic_lookup import DeterministicLookupService, detect_csv_table_mapping
from .retrieval import RetrievalService
from .storage import DocumentRecord, DocumentStore
from .tool_execution import ToolExecutionRouter
from .tools import AgentTool, format_retrieval_hits


def _terms(query: str) -> list[str]:
    return [term.lower() for term in query.split() if len(term) >= 3]


def _lookup_limit(query: str) -> int:
    return 50


def _record_matches(record: DocumentRecord, query: str, domains: set[str] | None = None) -> bool:
    terms = _terms(query)
    metadata = record.metadata
    if domains and str(metadata.get("domain", "")).lower() not in domains:
        return False
    haystack = " ".join(
        [
            record.title,
            record.key,
            record.content_type,
            json.dumps(metadata, sort_keys=True),
        ]
    ).lower()
    return not terms or any(term in haystack for term in terms)


def _document_payload(record: DocumentRecord) -> dict[str, Any]:
    governance = SourceGovernance.from_metadata(record.metadata)
    return {
        "title": record.title,
        "uri": record.uri,
        "content_type": record.content_type,
        "metadata": record.metadata,
        "governance": governance.as_dict(),
    }


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


def _run_deterministic_lookup(
    deterministic_lookup: DeterministicLookupService,
    query: str,
    user: HealthcareUserContext,
    *,
    limit: int,
    table_assets: list[dict[str, Any]],
) -> str:
    try:
        return deterministic_lookup.lookup(
            query,
            user,
            limit=limit,
            table_assets=table_assets,
        ).to_json()
    except TypeError:
        return deterministic_lookup.lookup(
            query,
            user,
            limit=limit,
            csv_assets=table_assets,
        ).to_json()


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

    def routed(
        name: str,
        local_run,
        *,
        extra_payload: dict[str, Any] | None = None,
    ):
        def run(query: str) -> str:
            return router.run(name, query, local_run, extra_payload=extra_payload)

        return run

    def document_search(query: str) -> str:
        """Semantic search over approved healthcare documents."""
        hits = access.filter_hits(user, retrieval.search(query))
        return format_retrieval_hits(hits)

    def policy_search(query: str) -> str:
        """Focused search over clinical/admin policies, SOPs, pathways, and guidelines."""
        hits = retrieval.search(query)
        filtered = []
        for hit in hits:
            metadata = hit.metadata
            domain = str(metadata.get("domain", "")).lower()
            document_type = str(metadata.get("document_type", "")).lower()
            if domain in {"clinical_policy", "admin_policy", "compliance"} or document_type in {
                "policy",
                "sop",
                "pathway",
                "guideline",
            }:
                filtered.append(hit)
        return format_retrieval_hits(access.filter_hits(user, filtered or hits))

    def catalogue_search(query: str) -> str:
        """Find departments, services, owners, systems, and approved tools."""
        records = access.filter_documents(user, documents.list_documents())
        matches = [
            _document_payload(record)
            for record in records
            if _record_matches(record, query, {"catalogue", "directory", "service", "systems"})
        ]
        return json.dumps(matches[:20], indent=2)

    def calendar_rota_lookup(query: str) -> str:
        """Lookup calendar, clinic, training, on-call, and rota data from controlled Postgres tables."""
        if deterministic_lookup is not None:
            return _run_deterministic_lookup(
                deterministic_lookup,
                query,
                user,
                limit=_lookup_limit(query),
                table_assets=deterministic_table_assets,
            )
        return json.dumps([], indent=2)

    def formulary_table_lookup(query: str) -> str:
        """Exact lookup over formulary, restricted medicines, codes, approvals, and structured facts."""
        if deterministic_lookup is not None:
            return _run_deterministic_lookup(
                deterministic_lookup,
                query,
                user,
                limit=_lookup_limit(query),
                table_assets=deterministic_table_assets,
            )
        return json.dumps([], indent=2)

    def safety_guard(query: str) -> str:
        """Detect clinical risk, missing sources, PHI exposure, or escalation needs."""
        assessment = safety.assess(query)
        return json.dumps(assessment.as_dict(), indent=2)

    def postgres_deterministic_lookup(query: str) -> str:
        """Exact Postgres lookup for patients, doctors, departments, contacts, appointments, wards, and formulary data."""
        if deterministic_lookup is None:
            return json.dumps(
                {
                    "category": "unavailable",
                    "message": "Postgres deterministic lookup is not configured.",
                    "rows": [],
                },
                indent=2,
            )
        return _run_deterministic_lookup(
            deterministic_lookup,
            query,
            user,
            limit=_lookup_limit(query),
            table_assets=deterministic_table_assets,
        )

    return [
        AgentTool(
            name="document_search",
            description="Semantic search over approved healthcare documents.",
            run=routed("document_search", document_search),
        ),
        AgentTool(
            name="policy_search",
            description="Focused retrieval over approved clinical/admin policies, SOPs, pathways, and guidelines.",
            run=routed("policy_search", policy_search),
        ),
        AgentTool(
            name="catalogue_search",
            description="Find healthcare departments, services, owners, systems, and approved tools.",
            run=routed("catalogue_search", catalogue_search),
        ),
        AgentTool(
            name="calendar_rota_lookup",
            description=(
                "Lookup clinics, training, and general rota schedules from approved structured sources. "
                "For staff availability, doctors, nurses, or on-call questions, prefer postgres_deterministic_lookup."
            ),
            run=routed(
                "calendar_rota_lookup",
                calendar_rota_lookup,
                extra_payload={"table_assets": deterministic_table_assets},
            ),
        ),
        AgentTool(
            name="formulary_table_lookup",
            description="Lookup restricted medicines, formulary rows, approval rules, codes, and structured facts.",
            run=routed(
                "formulary_table_lookup",
                formulary_table_lookup,
                extra_payload={"table_assets": deterministic_table_assets},
            ),
        ),
        AgentTool(
            name="postgres_deterministic_lookup",
            description=_deterministic_tool_description(deterministic_table_assets),
            run=routed(
                "postgres_deterministic_lookup",
                postgres_deterministic_lookup,
                extra_payload={"table_assets": deterministic_table_assets},
            ),
        ),
        AgentTool(
            name="safety_guard",
            description="Detect clinical risk, missing sources, PHI exposure, or escalation needs.",
            run=routed("safety_guard", safety_guard),
        ),
    ]
