from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import logging
from pathlib import PurePath
import re
import threading

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from ..agent import KnowledgeAgent
from ..auth import (
    AuthService,
    AuthenticationError,
    AuthorizationError,
    KNOWN_USER_ROLES,
    PasswordChangeRequiredError,
    UserManagementError,
)
from ..config import AppSettings
from ..deterministic_lookup import DeterministicLookupService, UnsupportedCsvLookupError, supported_csv_lookup_mappings
from ..healthcare import HealthcareUserContext
from ..history import PostgresChatHistoryRepository, create_chat_history_repository
from ..ingest import IngestionJob, postgres_table_manifest_records, table_lookup_manifest_record
from ..local_chroma import LocalChromaIngestionJob, LocalChromaRetrievalService
from ..models import (
    AdminDocumentUploadResponse,
    AdminDocumentMetadataUpdateRequest,
    AdminIngestionResponse,
    AdminDeleteIndexesRequest,
    AdminDeleteIndexesResponse,
    AdminPasswordResetRequest,
    AdminSystemEvalDataset,
    AdminSystemEvalDatasetsResponse,
    AdminSystemEvalRunListResponse,
    AdminSystemEvalRunRequest,
    AdminSystemEvalRunResponse,
    AdminToolExecutionSettings,
    AdminUserCreateRequest,
    AdminUserSummary,
    AdminUserUpdateRequest,
    AuthUserResponse,
    ChangePasswordRequest,
    ChatRequest,
    ChatResponse,
    ChatSessionDetail,
    ChatSessionSummary,
    GuardianNewsResponse,
    LoginRequest,
    LoginResponse,
    Source,
)
from ..news import GuardianNewsService
from ..observability import ObservabilityClient
from ..repositories.evaluations import PostgresEvaluationRepository
from ..retrieval import RetrievalService
from ..secrets import EnvSecretProvider, SecretProvider
from ..storage import DocumentStore, LocalDocumentStore
from ..twilio_whatsapp import (
    format_whatsapp_answer,
    parse_twilio_message,
    require_valid_twilio_request,
    send_twilio_whatsapp_message,
    split_whatsapp_messages,
    twiml_message,
    user_context_for_sender,
)
try:
    from system_evals import (
        EvaluationResult,
        bundled_dataset_ids,
        evaluate_response,
        load_bundled_dataset,
        markdown_report,
    )
    from system_evals.schema import summarize_results
except ModuleNotFoundError:  # pragma: no cover - local repo import layout
    from backend.system_evals import (
        EvaluationResult,
        bundled_dataset_ids,
        evaluate_response,
        load_bundled_dataset,
        markdown_report,
    )
    from backend.system_evals.schema import summarize_results


SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}
logger = logging.getLogger(__name__)
DOCUMENT_METADATA_VALUE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,63}$")
DASHBOARD_RANGE_WINDOWS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
}
DASHBOARD_RANGE_LABELS = {
    "30m": "30mins",
    "1h": "1hr",
    "3h": "3hr",
    "1d": "1 day",
    "3d": "3 days",
    "7d": "7 days",
    "all": "all time",
}
MANIFEST_SYNC_STATUS: dict[str, object] = {
    "checked": False,
    "up_to_date": False,
    "requires_attention": False,
    "message": "Manifest metadata has not been checked yet.",
}
MANIFEST_SYNC_LOCK = threading.Lock()


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings.from_env()


@lru_cache
def get_secret_provider() -> SecretProvider:
    settings = get_settings()
    if settings.use_local_resources():
        return EnvSecretProvider(settings)
    return SecretProvider(settings)


@lru_cache
def get_runtime_settings() -> AppSettings:
    settings = get_settings()
    tool_execution = get_secret_provider().load_tool_execution()
    return replace(
        settings,
        tool_execution_mode=tool_execution.tool_execution_mode,
        mcp_server_url=tool_execution.mcp_server_url,
        mcp_project_id=tool_execution.mcp_project_id,
        mcp_tool_timeout_seconds=tool_execution.mcp_tool_timeout_seconds,
        mcp_tool_fallback_to_local=tool_execution.mcp_tool_fallback_to_local,
    )


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService(get_secret_provider())


@lru_cache
def get_history_repository():
    settings = get_settings()
    if settings.use_local_resources():
        return PostgresChatHistoryRepository(settings)
    return create_chat_history_repository(settings)


@lru_cache
def get_evaluation_repository() -> PostgresEvaluationRepository:
    return PostgresEvaluationRepository(get_settings())


@lru_cache
def get_document_store() -> DocumentStore:
    settings = get_settings()
    if settings.use_local_resources():
        return LocalDocumentStore(settings)
    return DocumentStore(settings)


@lru_cache
def get_retrieval_service() -> RetrievalService:
    settings = get_settings()
    if settings.use_local_resources():
        return LocalChromaRetrievalService(settings, get_secret_provider())
    return RetrievalService(settings, get_secret_provider())


@lru_cache
def get_deterministic_lookup_service() -> DeterministicLookupService:
    return DeterministicLookupService(get_settings())


@lru_cache
def get_observability() -> ObservabilityClient:
    return ObservabilityClient(get_settings(), get_secret_provider())


@lru_cache
def get_news_service() -> GuardianNewsService:
    return GuardianNewsService(get_settings(), get_secret_provider())


def get_twilio_whatsapp_config():
    return get_secret_provider().load_twilio_whatsapp()


def create_ingestion_job():
    settings = get_settings()
    if settings.use_local_resources():
        return LocalChromaIngestionJob(settings, get_secret_provider(), get_deterministic_lookup_service())
    return IngestionJob(settings, get_secret_provider(), get_deterministic_lookup_service())


@lru_cache
def get_agent() -> KnowledgeAgent:
    return KnowledgeAgent(
        settings=get_runtime_settings(),
        secret_provider=get_secret_provider(),
        history=get_history_repository(),
        retrieval=get_retrieval_service(),
        documents=get_document_store(),
        observability=get_observability(),
    )


class InProcessEvaluationChatClient:
    def __init__(self, default_user: HealthcareUserContext):
        self.default_user = default_user

    def ask(self, case) -> dict[str, object]:
        eval_user = _system_eval_user_context(str(case.user or ""), self.default_user)
        result = get_agent().answer(
            user_id=eval_user.user_id,
            query=case.query,
            session_id=f"system-eval-{case.id}",
            user_context=eval_user,
            execution_mode=None,
        )
        return {
            "session_id": result.session_id,
            "answer": result.answer,
            "sources": list(result.sources),
            "tools_used": list(result.tools_used),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency_ms": result.latency_ms,
            "trace_id": result.trace_id,
            "safety": result.metadata.get("safety", {}),
            "audit_event": result.metadata.get("audit_event", {}),
            "performance": result.metadata.get("performance", {}),
            "latency_breakdown": result.metadata.get("latency_breakdown", {}),
        }


def _prepare_system_eval_cases(request: AdminSystemEvalRunRequest):
    cases = load_bundled_dataset(request.dataset_id)
    selected_categories = {category.strip() for category in request.categories if category.strip()}
    if selected_categories:
        cases = [case for case in cases if case.category in selected_categories]
    if request.limit:
        cases = cases[: request.limit]
    if not cases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No evaluation cases match the filters")
    effective_cases = [
        type(case)(**{**case.as_dict(), "user": request.user_id or case.user})
        for case in cases
    ]
    return selected_categories, effective_cases


def _system_eval_progress_summary(
    *,
    dataset_id: str,
    results,
    total_cases: int,
    current_case=None,
    current_index: int = 0,
    semantic_judge_enabled: bool = False,
) -> dict[str, object]:
    summary = summarize_results(dataset_id, list(results)).as_dict() if results else {
        "dataset_id": dataset_id,
        "total_cases": total_cases,
        "passed_cases": 0,
        "failed_cases": 0,
        "pass_rate": 0,
        "average_score": 0,
        "average_latency_ms": 0,
        "routing_accuracy": 0,
        "tool_accuracy": 0,
        "source_accuracy": 0,
        "safety_accuracy": 0,
    }
    completed = len(results)
    summary["total_cases"] = total_cases
    summary["completed_cases"] = completed
    summary["progress_total_cases"] = total_cases
    summary["progress_completed_cases"] = completed
    summary["progress_current_index"] = current_index
    summary["progress_current_case_id"] = getattr(current_case, "id", "") if current_case else ""
    summary["progress_current_query"] = getattr(current_case, "query", "") if current_case else ""
    summary["progress_percent"] = (completed / total_cases) if total_cases else 0
    if semantic_judge_enabled:
        summary["semantic_judge_enabled"] = True
        summary["semantic_judge_note"] = "Semantic judge is reserved for a future extension; hard assertions were used."
    return summary


def _run_system_eval_to_repository(
    *,
    run_id: str,
    dataset_id: str,
    cases,
    user: HealthcareUserContext,
    semantic_judge_enabled: bool,
) -> None:
    repository = get_evaluation_repository()
    client = InProcessEvaluationChatClient(user)
    results = []
    total_cases = len(cases)
    try:
        repository.update_run_progress(
            run_id=run_id,
            summary=_system_eval_progress_summary(
                dataset_id=dataset_id,
                results=results,
                total_cases=total_cases,
                current_case=cases[0] if cases else None,
                current_index=1 if cases else 0,
                semantic_judge_enabled=semantic_judge_enabled,
            ),
        )
        for index, case in enumerate(cases, start=1):
            repository.update_run_progress(
                run_id=run_id,
                summary=_system_eval_progress_summary(
                    dataset_id=dataset_id,
                    results=results,
                    total_cases=total_cases,
                    current_case=case,
                    current_index=index,
                    semantic_judge_enabled=semantic_judge_enabled,
                ),
            )
            try:
                response = client.ask(case)
                result = evaluate_response(case, response)
            except Exception as exc:
                result = EvaluationResult(
                    case=case,
                    passed=False,
                    score=0.0,
                    failure_reasons=(f"evaluation_error: {type(exc).__name__}: {exc}",),
                )
            results.append(result)
            repository.store_case_result(run_id=run_id, result=result.as_dict())
            repository.update_run_progress(
                run_id=run_id,
                summary=_system_eval_progress_summary(
                    dataset_id=dataset_id,
                    results=results,
                    total_cases=total_cases,
                    current_case=cases[index] if index < total_cases else None,
                    current_index=min(index + 1, total_cases),
                    semantic_judge_enabled=semantic_judge_enabled,
                ),
            )
        summary = summarize_results(dataset_id, results).as_dict()
        summary["completed_cases"] = total_cases
        summary["progress_total_cases"] = total_cases
        summary["progress_completed_cases"] = total_cases
        summary["progress_current_index"] = total_cases
        summary["progress_current_case_id"] = ""
        summary["progress_current_query"] = ""
        summary["progress_percent"] = 1
        if semantic_judge_enabled:
            summary["semantic_judge_enabled"] = True
            summary["semantic_judge_note"] = "Semantic judge is reserved for a future extension; hard assertions were used."
        report = markdown_report(run_id=run_id, summary=summary, results=results)
        status_value = "completed" if all(result.passed for result in results) else "completed_with_failures"
        repository.complete_run(
            run_id=run_id,
            status=status_value,
            summary=summary,
            report_markdown=report,
            results=[],
        )
    except Exception as exc:
        logger.exception("system_eval_run_failed run_id=%s", run_id)
        try:
            repository.fail_run(run_id, f"{type(exc).__name__}: {exc}")
        except Exception:
            pass


def _sync_table_metadata_manifest() -> dict[str, object]:
    with MANIFEST_SYNC_LOCK:
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            document_store = get_document_store()
            existing_documents = document_store.list_documents()
            existing_by_key = {document.key: document for document in existing_documents}
            expected_records = postgres_table_manifest_records(get_deterministic_lookup_service())
            expected_by_key = {str(record.get("key")): record for record in expected_records}
            missing_tables = [
                str(record.get("metadata", {}).get("source_table") or record.get("key"))
                for key, record in expected_by_key.items()
                if key not in existing_by_key
            ]
            stale_tables = []
            for key, record in expected_by_key.items():
                current = existing_by_key.get(key)
                if current is None:
                    continue
                expected_checksum = str(record.get("checksum") or record.get("metadata", {}).get("checksum") or "")
                current_checksum = str(current.metadata.get("checksum") or "")
                if expected_checksum and current_checksum and current_checksum != expected_checksum:
                    stale_tables.append(str(record.get("metadata", {}).get("source_table") or key))

            manifest_keys = set(existing_by_key)
            raw_keys = []
            if hasattr(document_store, "list_raw_document_keys"):
                raw_keys = list(document_store.list_raw_document_keys())
            missing_file_keys = sorted(str(key) for key in raw_keys if str(key) not in manifest_keys)

            upsert_result = {"updated": 0, "skipped": 0, "record_count": len(expected_records)}
            if hasattr(document_store, "upsert_manifest_records"):
                upsert_result = document_store.upsert_manifest_records(expected_records)
            else:
                for record in expected_records:
                    document_store.upsert_manifest_record(record)
                upsert_result = {"updated": len(expected_records), "skipped": 0, "record_count": len(expected_records)}

            if int(upsert_result.get("updated") or 0):
                try:
                    get_agent().invalidate_caches()
                except Exception:
                    pass

            was_stale = bool(missing_tables or stale_tables or missing_file_keys)
            if missing_file_keys:
                message = "Manifest is missing raw document entries; run document indexing to rebuild file metadata."
            elif missing_tables or stale_tables:
                message = "Postgres table metadata was missing or stale at startup and has been refreshed."
            else:
                message = "Manifest includes current Postgres table metadata."
            status_payload: dict[str, object] = {
                "checked": True,
                "checked_at": checked_at,
                "up_to_date": not missing_file_keys,
                "was_stale_at_startup": was_stale,
                "requires_attention": was_stale,
                "message": message,
                "expected_table_records": len(expected_records),
                "missing_tables": missing_tables,
                "stale_tables": stale_tables,
                "missing_file_keys": missing_file_keys[:25],
                "missing_file_count": len(missing_file_keys),
                "updated_records": int(upsert_result.get("updated") or 0),
                "skipped_records": int(upsert_result.get("skipped") or 0),
            }
        except Exception as exc:
            status_payload = {
                "checked": True,
                "checked_at": checked_at,
                "up_to_date": False,
                "was_stale_at_startup": True,
                "requires_attention": True,
                "message": "Manifest metadata sync failed.",
                "error": str(exc),
                "expected_table_records": 0,
                "missing_tables": [],
                "stale_tables": [],
                "missing_file_keys": [],
                "missing_file_count": 0,
                "updated_records": 0,
                "skipped_records": 0,
            }
        MANIFEST_SYNC_STATUS.clear()
        MANIFEST_SYNC_STATUS.update(status_payload)
        return dict(MANIFEST_SYNC_STATUS)


def _refresh_table_metadata_after_crm_mutation() -> dict[str, object]:
    sync_status = _sync_table_metadata_manifest()
    try:
        document_store = get_document_store()
        if hasattr(document_store, "invalidate_manifest_cache"):
            document_store.invalidate_manifest_cache()
    except Exception:
        pass
    try:
        get_agent().invalidate_caches()
    except Exception:
        pass
    return sync_status


def _run_backend_warmup() -> None:
    try:
        get_agent().warm_up()
    except Exception:
        return


@asynccontextmanager
async def lifespan(app: FastAPI):
    _sync_table_metadata_manifest()
    if get_settings().chat_warmup_enabled:
        threading.Thread(target=_run_backend_warmup, daemon=True).start()
    yield


app = FastAPI(
    title="Healthcare Knowledge Agent",
    version="0.1.0",
    lifespan=lifespan,
)
settings = get_settings()
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

security = HTTPBearer(auto_error=False)


def _login_response(result) -> LoginResponse:
    return LoginResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        username=result.username,
        roles=result.roles,
        departments=result.departments,
        password_change_required=result.password_change_required,
    )


def _admin_user_response(user) -> AdminUserSummary:
    return AdminUserSummary(
        username=user.username,
        roles=user.roles,
        departments=user.departments,
        password_change_required=user.password_change_required,
    )


def _auth_user_response(user: HealthcareUserContext) -> AuthUserResponse:
    return AuthUserResponse(
        username=user.user_id,
        roles=list(user.roles),
        departments=list(user.departments),
        password_change_required=user.password_change_required,
    )


def _tool_execution_settings_response() -> AdminToolExecutionSettings:
    provider = get_secret_provider()
    if hasattr(provider, "invalidate"):
        provider.invalidate(get_settings().app_secret_name)
    tool_execution = provider.load_tool_execution()
    return AdminToolExecutionSettings(
        tool_execution_mode=tool_execution.tool_execution_mode,
        mcp_server_url=tool_execution.mcp_server_url,
        mcp_project_id=tool_execution.mcp_project_id,
        mcp_tool_timeout_seconds=tool_execution.mcp_tool_timeout_seconds,
        mcp_tool_fallback_to_local=tool_execution.mcp_tool_fallback_to_local,
    )


def _refresh_tool_execution_runtime_caches() -> None:
    get_runtime_settings.cache_clear()
    get_agent.cache_clear()


def _safe_upload_filename(filename: str | None) -> str:
    raw_name = PurePath(filename or "").name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._-")
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must have a filename")
    suffix = PurePath(name).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supported file types are pdf, docx, txt, md, and csv",
        )
    return name


def _raw_document_key(filename: str) -> str:
    prefix = get_settings().s3_raw_prefix.strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def _normalize_document_metadata_value(value: str, field_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_:-]+", "_", str(value).strip().lower()).strip("_:-")
    if not normalized or not DOCUMENT_METADATA_VALUE_PATTERN.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document {field_name}",
        )
    return normalized


def _normalize_document_roles(roles: list[str]) -> list[str]:
    normalized = sorted({str(role).strip().lower() for role in roles if str(role).strip()})
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one access role is required")
    unknown_roles = [role for role in normalized if role not in KNOWN_USER_ROLES]
    if unknown_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown access role(s): {', '.join(unknown_roles)}",
        )
    return normalized


def _document_record_payload(document) -> dict[str, object]:
    return {
        "title": document.title,
        "key": document.key,
        "uri": document.uri,
        "content_type": document.content_type,
        "metadata": dict(document.metadata or {}),
        "chunk_count": int(document.chunk_count or 0),
        "ingestion_status": document.ingestion_status or "",
    }


def _empty_index_manifest() -> dict[str, object]:
    settings = get_settings()
    base: dict[str, object] = {
        "documents": [],
        "indexed_chunks": 0,
        "total_chunks": 0,
        "indexed_documents": 0,
        "skipped_documents": 0,
        "deleted_documents": 0,
        "deleted_chunks": 0,
    }
    if settings.use_local_resources():
        base.update(
            {
                "vector_backend": "chroma",
                "chroma_collection": settings.chroma_collection,
                "force_reindex": False,
            }
        )
    else:
        base.update(
            {
                "opensearch_index": settings.opensearch_index,
                "force_reindex": False,
            }
        )
    return base


def _tool_flow_from_metadata(metadata: dict[str, object], tools_used: list[str]) -> list[dict[str, object]]:
    existing = metadata.get("tool_flow")
    if isinstance(existing, list):
        return [dict(item) for item in existing if isinstance(item, dict)]

    guidance_items = metadata.get("catalog_guidance")
    remaining_guidance = [dict(item) for item in guidance_items if isinstance(item, dict)] if isinstance(guidance_items, list) else []
    flow: list[dict[str, object]] = []
    for tool in tools_used:
        guidance_index = next(
            (
                index
                for index, guidance in enumerate(remaining_guidance)
                if str(guidance.get("tool") or "") == tool
            ),
            None,
        )
        if guidance_index is None:
            flow.append({"tool": tool, "kind": "agent_tool", "selected_by_agent": True})
            continue
        guidance = remaining_guidance.pop(guidance_index)
        timing = guidance.get("timing_ms") if isinstance(guidance.get("timing_ms"), dict) else {}
        flow.append(
            {
                "tool": "document_catalog",
                "kind": "helper_tool",
                "label": "Shared helper tool",
                "helper_for": tool,
                "selected_by_agent": False,
                "query": guidance.get("query"),
                "candidate_count": guidance.get("candidate_count", 0),
                "candidate_keys": guidance.get("candidate_keys", []),
                "fallback_to_broad_search": guidance.get("fallback_to_broad_search", False),
                "latency_ms": int(timing.get("catalog_ms", 0)),
            }
        )
        flow.append(
            {
                "tool": tool,
                "kind": "agent_tool",
                "selected_by_agent": True,
                "query": guidance.get("query"),
                "source": "catalog_filtered_retrieval" if guidance.get("catalog_filter_applied") else "broad_retrieval",
                "candidate_count": guidance.get("candidate_count", 0),
                "returned_hits": int(timing.get("returned_hits", 0)),
                "latency_ms": int(timing.get("retrieval_search_ms", 0)),
            }
        )
    return flow


def _tool_flow_summary(tool_flow: list[dict[str, object]]) -> str:
    names = [str(item.get("tool") or "") for item in tool_flow if isinstance(item, dict) and item.get("tool")]
    return " -> ".join(names)


def _metric_ms(performance: dict[str, object], key: str) -> int:
    try:
        return int(performance.get(key) or 0)
    except Exception:
        return 0


def _tool_timing_totals(tool_timings: list[dict[str, object]]) -> dict[str, int]:
    totals: dict[str, int] = {
        "tool_count": len(tool_timings),
        "index_check_ms": 0,
        "index_created": 0,
        "catalog_ms": 0,
        "retrieval_search_ms": 0,
        "embedding_ms": 0,
        "opensearch_ms": 0,
        "neighbor_ms": 0,
        "access_filter_ms": 0,
        "total_ms": 0,
        "vector_hits": 0,
        "keyword_hits": 0,
        "neighbor_hits": 0,
        "returned_hits": 0,
    }
    for item in tool_timings:
        for key in totals:
            if key == "tool_count":
                continue
            try:
                totals[key] += int(item.get(key) or 0)
            except Exception:
                pass
    return totals


def _raw_timing_metrics(performance: dict[str, object]) -> dict[str, int]:
    timings: dict[str, int] = {}
    for key, value in performance.items():
        if key == "latency_breakdown":
            continue
        if key.endswith("_ms") or key == "total_ms":
            try:
                timings[key] = int(value or 0)
            except Exception:
                pass
    return dict(sorted(timings.items()))


def _dashboard_latency_breakdown(
    metadata: dict[str, object],
    performance: dict[str, object],
    latency_ms: int,
) -> dict[str, object]:
    existing = metadata.get("latency_breakdown")
    if isinstance(existing, dict):
        if isinstance(existing.get("sections"), dict):
            return existing
    existing = performance.get("latency_breakdown")
    if isinstance(existing, dict):
        if isinstance(existing.get("sections"), dict):
            return existing

    tool_timings = [dict(item) for item in performance.get("tool_timings") or [] if isinstance(item, dict)]
    tool_totals = _tool_timing_totals(tool_timings)
    trace_setup_ms = _metric_ms(performance, "langfuse_trace_create_ms") + _metric_ms(
        performance,
        "langfuse_trace_enter_ms",
    )
    top_level = {
        "history_load_ms": _metric_ms(performance, "history_load_ms"),
        "trace_setup_ms": trace_setup_ms,
        "prompt_load_ms": _metric_ms(performance, "langfuse_prompt_ms"),
        "initial_safety_ms": _metric_ms(performance, "initial_safety_ms"),
        "agent_execution_ms": _metric_ms(performance, "agent_execution_ms"),
        "response_guardrail_ms": _metric_ms(performance, "response_guardrail_llm_ms"),
        "final_safety_ms": _metric_ms(performance, "final_safety_ms"),
        "history_save_ms": _metric_ms(performance, "history_save_ms"),
    }
    top_level["unattributed_ms"] = max(0, int(latency_ms) - sum(top_level.values()))
    agent_detail = {
        "llm_setup_ms": _metric_ms(performance, "llm_setup_ms"),
        "fast_llm_setup_ms": _metric_ms(performance, "fast_llm_setup_ms"),
        "langfuse_callbacks_ms": _metric_ms(performance, "langfuse_callbacks_ms"),
        "llm_tool_choice_ms": _metric_ms(performance, "llm_tool_choice_ms"),
        "llm_final_ms": _metric_ms(performance, "llm_final_ms"),
        "llm_direct_answer_ms": _metric_ms(performance, "llm_direct_answer_ms"),
        "llm_total_ms": _metric_ms(performance, "llm_tool_choice_ms")
        + _metric_ms(performance, "llm_final_ms")
        + _metric_ms(performance, "llm_direct_answer_ms"),
        "catalog_ms": _metric_ms(performance, "catalog_ms"),
        "index_check_ms": _metric_ms(performance, "index_check_ms"),
        "retrieval_search_ms": _metric_ms(performance, "retrieval_search_ms"),
        "embedding_ms": _metric_ms(performance, "embedding_ms"),
        "opensearch_ms": _metric_ms(performance, "opensearch_ms"),
        "neighbor_ms": _metric_ms(performance, "neighbor_ms"),
        "access_filter_ms": _metric_ms(performance, "access_filter_ms"),
    }
    sections = {
        "history": {
            "load_ms": _metric_ms(performance, "history_load_ms"),
            "save_ms": _metric_ms(performance, "history_save_ms"),
            "save_background": bool(performance.get("history_save_background")),
        },
        "observability": {
            "langfuse_trace_create_ms": _metric_ms(performance, "langfuse_trace_create_ms"),
            "langfuse_trace_enter_ms": _metric_ms(performance, "langfuse_trace_enter_ms"),
            "trace_setup_ms": trace_setup_ms,
            "langfuse_prompt_ms": _metric_ms(performance, "langfuse_prompt_ms"),
            "langfuse_callbacks_ms": _metric_ms(performance, "langfuse_callbacks_ms"),
        },
        "safety_and_guardrail": {
            "initial_safety_ms": _metric_ms(performance, "initial_safety_ms"),
            "response_guardrail_llm_ms": _metric_ms(performance, "response_guardrail_llm_ms"),
            "response_guardrail_applied": bool(performance.get("response_guardrail_applied")),
            "response_guardrail_changed": bool(performance.get("response_guardrail_changed")),
            "response_guardrail_reason": str(performance.get("response_guardrail_reason") or ""),
            "final_safety_ms": _metric_ms(performance, "final_safety_ms"),
        },
        "agent_orchestration": {
            "agent_execution_ms": _metric_ms(performance, "agent_execution_ms"),
            "agent_mode": str(performance.get("agent_mode") or ""),
            "planned_tools": list(performance.get("planned_tools") or []),
            "llm_call_count": int(performance.get("llm_call_count") or 0),
        },
        "llm": {
            "llm_setup_ms": _metric_ms(performance, "llm_setup_ms"),
            "llm_cache_hit": bool(performance.get("llm_cache_hit")),
            "llm_setup_cold_start": bool(performance.get("llm_setup_cold_start")),
            "fast_llm_setup_ms": _metric_ms(performance, "fast_llm_setup_ms"),
            "fast_llm_cache_hit": bool(performance.get("fast_llm_cache_hit")),
            "fast_llm_setup_cold_start": bool(performance.get("fast_llm_setup_cold_start")),
            "llm_tool_choice_ms": _metric_ms(performance, "llm_tool_choice_ms"),
            "llm_final_ms": _metric_ms(performance, "llm_final_ms"),
            "llm_direct_answer_ms": _metric_ms(performance, "llm_direct_answer_ms"),
            "llm_total_ms": agent_detail["llm_total_ms"],
        },
        "retrieval_and_catalog": {
            "catalog_ms": _metric_ms(performance, "catalog_ms"),
            "index_check_ms": _metric_ms(performance, "index_check_ms"),
            "index_created": tool_totals["index_created"],
            "retrieval_search_ms": _metric_ms(performance, "retrieval_search_ms"),
            "embedding_ms": _metric_ms(performance, "embedding_ms"),
            "opensearch_ms": _metric_ms(performance, "opensearch_ms"),
            "neighbor_ms": _metric_ms(performance, "neighbor_ms"),
            "access_filter_ms": _metric_ms(performance, "access_filter_ms"),
            "tool_total_ms": tool_totals["total_ms"],
            "vector_hits": tool_totals["vector_hits"],
            "keyword_hits": tool_totals["keyword_hits"],
            "neighbor_hits": tool_totals["neighbor_hits"],
            "returned_hits": tool_totals["returned_hits"],
        },
    }
    return {
        "total_ms": int(latency_ms),
        "top_level": top_level,
        "agent_detail": agent_detail,
        "sections": sections,
        "raw_timing_metrics": _raw_timing_metrics(performance),
        "tool_timing_totals": tool_totals,
        "tool_timings": tool_timings,
    }


def _latency_breakdown_summary(latency_breakdown: dict[str, object]) -> str:
    top_level = latency_breakdown.get("top_level")
    if not isinstance(top_level, dict):
        return ""
    labels = {
        "agent_execution_ms": "agent",
        "history_load_ms": "history load",
        "trace_setup_ms": "trace",
        "prompt_load_ms": "prompt",
        "initial_safety_ms": "initial safety",
        "response_guardrail_ms": "guardrail",
        "final_safety_ms": "final safety",
        "history_save_ms": "history save",
        "unattributed_ms": "other",
    }
    values: list[tuple[str, int]] = []
    for key, label in labels.items():
        try:
            value = int(top_level.get(key) or 0)
        except Exception:
            value = 0
        if value:
            values.append((label, value))
    values.sort(key=lambda item: item[1], reverse=True)
    return ", ".join(f"{label} {value} ms" for label, value in values[:3])


def _percentile_ms(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(int(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    bounded = min(100.0, max(0.0, float(percentile)))
    rank = (bounded / 100.0) * (len(ordered) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = rank - lower_index
    return int(round(ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction))


def _estimated_llm_cost_usd(input_tokens: int, output_tokens: int) -> float:
    settings = get_settings()
    return round(
        (
            max(0, int(input_tokens)) * float(settings.llm_input_cost_per_million_tokens)
            + max(0, int(output_tokens)) * float(settings.llm_output_cost_per_million_tokens)
        )
        / 1_000_000,
        6,
    )


def _parse_dashboard_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dashboard_cutoff(range_key: str) -> datetime | None:
    window = DASHBOARD_RANGE_WINDOWS.get(range_key)
    if window is None:
        return None
    return datetime.now(timezone.utc) - window


def _dashboard_registered_users() -> list[str]:
    try:
        return [managed_user.username for managed_user in get_auth_service().list_users()]
    except Exception:
        return []


def current_user_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> HealthcareUserContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        claims = get_auth_service().verify_token_claims(credentials.credentials)
        return HealthcareUserContext.from_claims(claims)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def active_user_context(
    user: HealthcareUserContext = Depends(current_user_context),
) -> HealthcareUserContext:
    try:
        get_auth_service().ensure_password_change_not_required(
            {
                "password_change_required": user.password_change_required,
            }
        )
        return user
    except PasswordChangeRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def admin_user_context(
    user: HealthcareUserContext = Depends(active_user_context),
) -> HealthcareUserContext:
    try:
        get_auth_service().ensure_admin(
            {
                "roles": list(user.roles),
                "password_change_required": user.password_change_required,
            }
        )
        return user
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def _system_eval_user_context(user_id: str, fallback: HealthcareUserContext) -> HealthcareUserContext:
    requested = str(user_id or "").strip()
    if not requested:
        return fallback
    try:
        for managed_user in get_auth_service().list_users():
            if managed_user.username == requested:
                return HealthcareUserContext(
                    user_id=managed_user.username,
                    roles=tuple(managed_user.roles),
                    departments=tuple(managed_user.departments),
                    password_change_required=managed_user.password_change_required,
                )
    except Exception:
        pass
    return fallback


def current_user(user: HealthcareUserContext = Depends(active_user_context)) -> str:
    return user.user_id


@app.get("/health")
def health() -> dict[str, object]:
    agent = get_agent()
    settings_summary = get_runtime_settings().public_summary()
    try:
        settings_summary["guardian_api_configured"] = str(get_news_service().api_key_configured())
    except Exception:
        pass
    return {
        "status": "ok",
        "settings": settings_summary,
        "registered_tools": agent.registered_tool_names(),
        "warmup": agent.warmup_status(),
    }


@app.get("/system/manifest-status")
def system_manifest_status(user: HealthcareUserContext = Depends(active_user_context)) -> dict[str, object]:
    if not MANIFEST_SYNC_STATUS.get("checked"):
        _sync_table_metadata_manifest()
    return dict(MANIFEST_SYNC_STATUS)


@app.get("/news", response_model=GuardianNewsResponse)
def guardian_news() -> GuardianNewsResponse:
    return GuardianNewsResponse(**get_news_service().get_payload())


@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    try:
        return _login_response(get_auth_service().login(request.username, request.password))
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Document ingestion failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/auth/me", response_model=AuthUserResponse)
def auth_me(user: HealthcareUserContext = Depends(current_user_context)) -> AuthUserResponse:
    return _auth_user_response(user)


@app.post("/auth/change-password", response_model=LoginResponse)
def change_password(
    request: ChangePasswordRequest,
    user: HealthcareUserContext = Depends(current_user_context),
) -> LoginResponse:
    try:
        return _login_response(
            get_auth_service().change_password(
                user.user_id,
                request.current_password,
                request.new_password,
            )
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except UserManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/admin/users", response_model=list[AdminUserSummary])
def list_admin_users(
    user: HealthcareUserContext = Depends(admin_user_context),
) -> list[AdminUserSummary]:
    return [_admin_user_response(admin_user) for admin_user in get_auth_service().list_users()]


@app.post("/admin/users", response_model=AdminUserSummary, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    request: AdminUserCreateRequest,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminUserSummary:
    try:
        created = get_auth_service().create_user(
            request.username,
            request.temporary_password,
            request.roles,
            request.departments,
        )
        return _admin_user_response(created)
    except UserManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.patch("/admin/users/{username}", response_model=AdminUserSummary)
def update_admin_user(
    username: str,
    request: AdminUserUpdateRequest,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminUserSummary:
    try:
        updated = get_auth_service().update_user(
            username,
            roles=request.roles,
            departments=request.departments,
        )
        return _admin_user_response(updated)
    except UserManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/admin/users/{username}/reset-password", response_model=AdminUserSummary)
def reset_admin_user_password(
    username: str,
    request: AdminPasswordResetRequest,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminUserSummary:
    try:
        updated = get_auth_service().reset_password(username, request.temporary_password)
        return _admin_user_response(updated)
    except UserManagementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/admin/settings/tool-execution", response_model=AdminToolExecutionSettings)
def get_admin_tool_execution_settings(
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminToolExecutionSettings:
    try:
        return _tool_execution_settings_response()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.patch("/admin/settings/tool-execution", response_model=AdminToolExecutionSettings)
def update_admin_tool_execution_settings(
    request: AdminToolExecutionSettings,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminToolExecutionSettings:
    mode = request.tool_execution_mode.strip().lower()
    if mode not in {"local", "mcp"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tool_execution_mode must be local or mcp")

    mcp_server_url = request.mcp_server_url.strip()
    mcp_project_id = request.mcp_project_id.strip()
    if mode == "mcp" and not mcp_server_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mcp_server_url is required for MCP mode")
    if not mcp_project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mcp_project_id is required")

    provider = get_secret_provider()
    secret_name = get_settings().app_secret_name
    try:
        payload = dict(provider.get_json(secret_name))
        payload.update(
            {
                "tool_execution_mode": mode,
                "mcp_server_url": mcp_server_url,
                "mcp_project_id": mcp_project_id,
                "mcp_tool_timeout_seconds": int(request.mcp_tool_timeout_seconds),
                "mcp_tool_fallback_to_local": bool(request.mcp_tool_fallback_to_local),
            }
        )
        provider.put_json(secret_name, payload)
        if hasattr(provider, "invalidate"):
            provider.invalidate(secret_name)
        _refresh_tool_execution_runtime_caches()
        return _tool_execution_settings_response()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/admin/documents/upload", response_model=AdminDocumentUploadResponse)
async def upload_admin_document(
    file: UploadFile = File(...),
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminDocumentUploadResponse:
    filename = _safe_upload_filename(file.filename)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if filename.lower().endswith(".csv"):
        key = _raw_document_key(filename)
        content_type = file.content_type or "text/csv"
        try:
            sync_result = get_deterministic_lookup_service().ingest_uploaded_csv(filename, data)
        except UnsupportedCsvLookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": str(exc),
                    "supported_mappings": supported_csv_lookup_mappings(),
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        try:
            get_document_store().upload_document(key, data, content_type)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        try:
            document_store = get_document_store()
            if hasattr(document_store, "upsert_manifest_record"):
                document_store.upsert_manifest_record(
                    table_lookup_manifest_record(
                        key,
                        data,
                        sync_result,
                        content_type,
                        uri=f"s3://{get_settings().s3_bucket}/{key}",
                    )
                )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return AdminDocumentUploadResponse(
            key=key,
            uri=f"s3://{get_settings().s3_bucket}/{key}",
            content_type=content_type,
            size_bytes=len(data),
        )
    key = _raw_document_key(filename)
    content_type = file.content_type or "application/octet-stream"
    try:
        get_document_store().upload_document(key, data, content_type)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return AdminDocumentUploadResponse(
        key=key,
        uri=f"s3://{get_settings().s3_bucket}/{key}",
        content_type=content_type,
        size_bytes=len(data),
    )


@app.patch("/admin/documents/metadata")
def update_admin_document_metadata(
    request: AdminDocumentMetadataUpdateRequest,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    category = _normalize_document_metadata_value(request.category, "category")
    document_type = _normalize_document_metadata_value(request.document_type, "type")
    allowed_roles = _normalize_document_roles(request.allowed_roles)
    try:
        document_store = get_document_store()
        documents = document_store.list_documents()
        target = next(
            (
                document
                for document in documents
                if document.key == request.key or document.uri == request.key or document.title == request.key
            ),
            None,
        )
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        metadata = dict(target.metadata or {})
        metadata["domain"] = category
        metadata["document_type"] = document_type
        metadata["allowed_roles"] = allowed_roles
        updated_record = {
            "title": target.title,
            "key": target.key,
            "uri": target.uri,
            "content_type": target.content_type,
            "metadata": metadata,
            "chunk_count": int(target.chunk_count or 0),
            "ingestion_status": "metadata_updated",
        }
        if not hasattr(document_store, "upsert_manifest_record"):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Document manifest is read-only")
        document_store.upsert_manifest_record(updated_record)
        if hasattr(document_store, "invalidate_manifest_cache"):
            document_store.invalidate_manifest_cache()
        agent = get_agent()
        if hasattr(agent, "invalidate_caches"):
            agent.invalidate_caches()
        return updated_record
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.delete("/admin/documents/{document_key:path}")
def delete_admin_document(
    document_key: str,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    try:
        document_store = get_document_store()
        documents = document_store.list_documents()
        target = next(
            (
                document
                for document in documents
                if document.key == document_key or document.uri == document_key or document.title == document_key
            ),
            None,
        )
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        if not hasattr(document_store, "delete_document"):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Document store is read-only")
        result = document_store.delete_document(target.key)
        if hasattr(document_store, "invalidate_manifest_cache"):
            document_store.invalidate_manifest_cache()
        agent = get_agent()
        if hasattr(agent, "invalidate_caches"):
            agent.invalidate_caches()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/admin/documents/delete-indexes", response_model=AdminDeleteIndexesResponse)
def delete_admin_document_indexes(
    request: AdminDeleteIndexesRequest,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminDeleteIndexesResponse:
    try:
        get_auth_service().verify_user_password(user.user_id, request.admin_password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        retrieval_service = get_retrieval_service()
        deleted_chunks = 0
        deleted_lookup_rows = 0
        if hasattr(retrieval_service, "delete_all_indexes"):
            deleted_chunks = int(retrieval_service.delete_all_indexes())
        elif hasattr(retrieval_service, "invalidate_cache"):
            retrieval_service.invalidate_cache()

        document_store = get_document_store()
        if hasattr(document_store, "replace_manifest"):
            document_store.replace_manifest(_empty_index_manifest())
        if hasattr(document_store, "invalidate_manifest_cache"):
            document_store.invalidate_manifest_cache()

        agent = get_agent()
        if hasattr(agent, "invalidate_caches"):
            agent.invalidate_caches()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return AdminDeleteIndexesResponse(
        deleted_chunks=deleted_chunks,
        deleted_lookup_rows=deleted_lookup_rows,
        manifest_cleared=True,
        backend="chroma" if get_settings().use_local_resources() else "opensearch",
        raw_documents_preserved=True,
        deterministic_lookup_preserved=True,
    )


@app.post("/admin/documents/ingest", response_model=AdminIngestionResponse)
def ingest_admin_documents(
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminIngestionResponse:
    try:
        result = create_ingestion_job().run()
        document_store = get_document_store()
        if hasattr(document_store, "invalidate_manifest_cache"):
            document_store.invalidate_manifest_cache()
        retrieval_service = get_retrieval_service()
        if hasattr(retrieval_service, "invalidate_cache"):
            retrieval_service.invalidate_cache()
        agent = get_agent()
        if hasattr(agent, "invalidate_caches"):
            agent.invalidate_caches()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return AdminIngestionResponse(
        opensearch_index=result.get("opensearch_index"),
        previous_opensearch_index=result.get("previous_opensearch_index"),
        force_reindex=bool(result.get("force_reindex", False)),
        documents=list(result.get("documents", [])),
        indexed_chunks=int(result.get("indexed_chunks", 0)),
        total_chunks=int(result.get("total_chunks", 0)),
        indexed_documents=int(result.get("indexed_documents", 0)),
        skipped_documents=int(result.get("skipped_documents", 0)),
        deleted_documents=int(result.get("deleted_documents", 0)),
        deleted_chunks=int(result.get("deleted_chunks", 0)),
    )


@app.get("/admin/dashboard")
def admin_dashboard(
    limit: int = Query(default=500, ge=1, le=2000),
    range: str = Query(default="all"),
    user_id: str = Query(default="all"),
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    range_key = range if range in DASHBOARD_RANGE_LABELS else "all"
    selected_user = user_id.strip() if user_id else "all"
    registered_users = _dashboard_registered_users()
    if selected_user != "all" and registered_users and selected_user not in registered_users:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown dashboard user filter")
    cutoff = _dashboard_cutoff(range_key)
    interactions = get_history_repository().list_recent_interactions(limit=limit)
    rows: list[dict[str, object]] = []
    tool_counts: dict[str, int] = {}
    tool_flow_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    user_counts: dict[str, int] = {}
    model_counts: dict[str, int] = {}
    latencies: list[int] = []
    input_tokens: list[int] = []
    output_tokens: list[int] = []
    total_tokens: list[int] = []
    query_costs_usd: list[float] = []
    ragas_values: dict[str, list[float]] = {
        "ragas_faithfulness": [],
        "ragas_answer_relevancy": [],
        "ragas_context_precision": [],
        "ragas_context_recall": [],
    }
    guardrail_count = 0
    total_sources = 0

    for interaction in interactions:
        if selected_user != "all" and interaction.user_id != selected_user:
            continue
        if cutoff is not None:
            created_at = _parse_dashboard_datetime(interaction.created_at)
            if created_at is None or created_at < cutoff:
                continue
        metadata = interaction.metadata or {}
        performance = metadata.get("performance") if isinstance(metadata.get("performance"), dict) else {}
        tools_used = [str(tool) for tool in metadata.get("tools_used", [])]
        tool_flow = _tool_flow_from_metadata(metadata, tools_used)
        agent_flow = metadata.get("agent_flow", []) if isinstance(metadata.get("agent_flow"), list) else []
        agents_used = [
            str(agent)
            for agent in metadata.get("agents_used", [])
            if str(agent)
        ] if isinstance(metadata.get("agents_used"), list) else []
        if not agents_used:
            agents_used = [
                str(step.get("agent"))
                for step in agent_flow
                if isinstance(step, dict)
                and step.get("agent")
                and str(step.get("agent")) != "SupervisorAgent"
            ]
            agents_used = list(dict.fromkeys(agents_used))
        supervisor_decisions = (
            metadata.get("supervisor_decisions", [])
            if isinstance(metadata.get("supervisor_decisions"), list)
            else []
        )
        agent_latencies_ms = (
            metadata.get("agent_latencies_ms", {})
            if isinstance(metadata.get("agent_latencies_ms"), dict)
            else {}
        )
        agent_errors = metadata.get("agent_errors", []) if isinstance(metadata.get("agent_errors"), list) else []
        sources = metadata.get("sources", []) if isinstance(metadata.get("sources"), list) else []
        chat_execution_mode = str(metadata.get("chat_execution_mode") or "supervisor")
        chat_execution_mode_label = str(metadata.get("chat_execution_mode_label") or "Supervisor")
        tool_execution_mode = str(
            metadata.get("tool_execution_mode")
            or performance.get("tool_execution_mode")
            or ""
        )
        tool_execution_location = str(
            metadata.get("tool_execution_location")
            or performance.get("tool_execution_location")
            or ("MCP server" if tool_execution_mode == "mcp" else "Backend local tools" if tool_execution_mode else "Unknown")
        )
        mcp_server_url = str(metadata.get("mcp_server_url") or performance.get("mcp_server_url") or "")
        mcp_project_id = str(metadata.get("mcp_project_id") or performance.get("mcp_project_id") or "")
        tool_execution_records = (
            metadata.get("tool_execution_records")
            if isinstance(metadata.get("tool_execution_records"), list)
            else performance.get("tool_execution_records")
            if isinstance(performance.get("tool_execution_records"), list)
            else []
        )
        latency_ms = int(metadata.get("latency_ms") or performance.get("total_ms") or 0)
        latency_breakdown = _dashboard_latency_breakdown(metadata, performance, latency_ms)
        input_token_count = int(metadata.get("input_tokens") or 0)
        output_token_count = int(metadata.get("output_tokens") or 0)
        total_token_count = input_token_count + output_token_count
        estimated_cost_usd = _estimated_llm_cost_usd(input_token_count, output_token_count)
        model = str(metadata.get("model") or get_settings().azure_openai_deployment or "unknown")
        guardrail_applied = bool(metadata.get("guardrail_applied") or performance.get("response_guardrail_applied"))
        ragas_scores = metadata.get("ragas") if isinstance(metadata.get("ragas"), dict) else {}

        user_counts[interaction.user_id] = user_counts.get(interaction.user_id, 0) + 1
        model_counts[model] = model_counts.get(model, 0) + 1
        total_sources += len(sources)
        if latency_ms:
            latencies.append(latency_ms)
        if input_token_count:
            input_tokens.append(input_token_count)
        if output_token_count:
            output_tokens.append(output_token_count)
        if total_token_count:
            total_tokens.append(total_token_count)
        query_costs_usd.append(estimated_cost_usd)
        if guardrail_applied:
            guardrail_count += 1
        for score_name in ragas_values:
            try:
                value = ragas_scores.get(score_name)
                if value is not None:
                    ragas_values[score_name].append(float(value))
            except Exception:
                pass
        for tool in tools_used:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        for step in tool_flow:
            tool_name = str(step.get("tool") or "")
            if tool_name:
                tool_flow_counts[tool_name] = tool_flow_counts.get(tool_name, 0) + 1
        for agent in agents_used:
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

        rows.append(
            {
                "user_id": interaction.user_id,
                "session_id": interaction.session_id,
                "created_at": interaction.created_at,
                "query": interaction.question,
                "answer": interaction.answer,
                "trace_id": metadata.get("trace_id"),
                "model": model,
                "tools_used": tools_used,
                "tool_flow": tool_flow,
                "tool_flow_summary": _tool_flow_summary(tool_flow),
                "agent_flow": agent_flow,
                "agents_used": agents_used,
                "agent_flow_summary": " -> ".join(agents_used),
                "supervisor_decisions": supervisor_decisions,
                "agent_latencies_ms": agent_latencies_ms,
                "agent_errors": agent_errors,
                "chat_execution_mode": chat_execution_mode,
                "chat_execution_mode_label": chat_execution_mode_label,
                "tool_execution_mode": tool_execution_mode,
                "tool_execution_location": tool_execution_location,
                "tool_execution_records": tool_execution_records,
                "mcp_server_url": mcp_server_url,
                "mcp_project_id": mcp_project_id,
                "source_count": len(sources),
                "source_document_keys": metadata.get("source_document_keys", []),
                "latency_ms": latency_ms,
                "latency_breakdown": latency_breakdown,
                "latency_breakdown_summary": _latency_breakdown_summary(latency_breakdown),
                "input_tokens": input_token_count,
                "output_tokens": output_token_count,
                "total_tokens": total_token_count,
                "estimated_cost_usd": estimated_cost_usd,
                "agent_mode": performance.get("agent_mode"),
                "ragas": ragas_scores,
                "ragas_status": metadata.get("ragas_status"),
                "ragas_provider": metadata.get("ragas_provider"),
                "ragas_error": metadata.get("ragas_error"),
                "langfuse_ragas_published": metadata.get("langfuse_ragas_published"),
                "langfuse_ragas_error": metadata.get("langfuse_ragas_error"),
                "guardrail_applied": guardrail_applied,
                "guardrail_reason": metadata.get("guardrail_reason") or performance.get("response_guardrail_reason"),
                "safety": metadata.get("safety", {}),
            }
        )

    summary = {
        "total_queries": len(rows),
        "unique_users": len(user_counts),
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "p50_latency_ms": _percentile_ms(latencies, 50),
        "p95_latency_ms": _percentile_ms(latencies, 95),
        "avg_input_tokens": int(sum(input_tokens) / len(input_tokens)) if input_tokens else 0,
        "avg_output_tokens": int(sum(output_tokens) / len(output_tokens)) if output_tokens else 0,
        "avg_total_tokens": int(sum(total_tokens) / len(total_tokens)) if total_tokens else 0,
        "total_estimated_cost_usd": round(sum(query_costs_usd), 6),
        "avg_estimated_cost_usd": round(sum(query_costs_usd) / len(query_costs_usd), 6) if query_costs_usd else 0,
        "avg_sources_per_query": (total_sources / len(rows)) if rows else 0,
        "guardrail_trigger_count": guardrail_count,
        "tool_counts": tool_counts,
        "tool_flow_counts": tool_flow_counts,
        "agent_counts": agent_counts,
        "user_counts": user_counts,
        "model_counts": model_counts,
        "ragas": {
            score_name: (sum(values) / len(values) if values else None)
            for score_name, values in ragas_values.items()
        },
    }
    return {
        "summary": summary,
        "queries": rows,
        "filters": {
            "range": range_key,
            "range_label": DASHBOARD_RANGE_LABELS.get(range_key, "all time"),
            "user_id": selected_user,
            "available_ranges": [
                {"value": key, "label": label}
                for key, label in DASHBOARD_RANGE_LABELS.items()
            ],
            "users": registered_users,
        },
    }


@app.get("/admin/evaluations/datasets", response_model=AdminSystemEvalDatasetsResponse)
def admin_evaluation_datasets(
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminSystemEvalDatasetsResponse:
    datasets: list[AdminSystemEvalDataset] = []
    for dataset_id in bundled_dataset_ids():
        try:
            cases = load_bundled_dataset(dataset_id)
            datasets.append(
                AdminSystemEvalDataset(
                    dataset_id=dataset_id,
                    case_count=len(cases),
                    categories=sorted({case.category for case in cases}),
                )
            )
        except Exception:
            logger.exception("system_eval_dataset_load_failed dataset=%s", dataset_id)
    return AdminSystemEvalDatasetsResponse(datasets=datasets)


@app.post("/admin/evaluations/runs", response_model=AdminSystemEvalRunResponse)
def admin_create_evaluation_run(
    request: AdminSystemEvalRunRequest,
    background_tasks: BackgroundTasks,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminSystemEvalRunResponse:
    run_id = ""
    try:
        selected_categories, effective_cases = _prepare_system_eval_cases(request)

        runtime_settings = get_runtime_settings()
        repository = get_evaluation_repository()
        run_id = repository.create_run(
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_id,
            environment=get_settings().app_env,
            tool_mode=runtime_settings.tool_execution_mode,
            requested_by=user.user_id,
            semantic_judge_enabled=request.semantic_judge_enabled,
            category_filter=sorted(selected_categories),
            user_filter=request.user_id,
        )
        initial_summary = _system_eval_progress_summary(
            dataset_id=request.dataset_id,
            results=[],
            total_cases=len(effective_cases),
            current_case=effective_cases[0],
            current_index=1,
            semantic_judge_enabled=request.semantic_judge_enabled,
        )
        repository.update_run_progress(run_id=run_id, summary=initial_summary)
        if request.async_run:
            background_tasks.add_task(
                _run_system_eval_to_repository,
                run_id=run_id,
                dataset_id=request.dataset_id,
                cases=effective_cases,
                user=user,
                semantic_judge_enabled=request.semantic_judge_enabled,
            )
            return AdminSystemEvalRunResponse(
                run_id=run_id,
                dataset_id=request.dataset_id,
                status="running",
                summary=initial_summary,
                cases=[],
            )

        _run_system_eval_to_repository(
            run_id=run_id,
            dataset_id=request.dataset_id,
            cases=effective_cases,
            user=user,
            semantic_judge_enabled=request.semantic_judge_enabled,
        )
        stored = repository.get_run(run_id) or {}
        return AdminSystemEvalRunResponse(
            run_id=run_id,
            dataset_id=request.dataset_id,
            status=str(stored.get("status") or status_value),
            summary=dict(stored.get("summary") or summary),
            cases=list(stored.get("cases") or []),
        )
    except HTTPException:
        raise
    except Exception as exc:
        if run_id:
            try:
                get_evaluation_repository().fail_run(run_id, f"{type(exc).__name__}: {exc}")
            except Exception:
                pass
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/admin/evaluations/runs", response_model=AdminSystemEvalRunListResponse)
def admin_list_evaluation_runs(
    limit: int = Query(default=25, ge=1, le=100),
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminSystemEvalRunListResponse:
    try:
        return AdminSystemEvalRunListResponse(runs=get_evaluation_repository().list_runs(limit=limit))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/admin/evaluations/runs/{run_id}/report")
def admin_get_evaluation_report(
    run_id: str,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> Response:
    try:
        report = get_evaluation_repository().get_report(run_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found")
    return Response(content=report, media_type="text/markdown")


@app.get("/admin/evaluations/runs/{run_id}", response_model=AdminSystemEvalRunResponse)
def admin_get_evaluation_run(
    run_id: str,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> AdminSystemEvalRunResponse:
    try:
        stored = get_evaluation_repository().get_run(run_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found")
    return AdminSystemEvalRunResponse(
        run_id=str(stored.get("run_id") or run_id),
        dataset_id=str(stored.get("dataset_id") or ""),
        status=str(stored.get("status") or ""),
        summary=dict(stored.get("summary") or {}),
        cases=list(stored.get("cases") or []),
    )


@app.post("/admin/warmup")
def admin_warmup(
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    return get_agent().warm_up()


@app.get("/admin/patient-details")
def admin_patient_details(
    q: str = Query(default="", max_length=100),
    patient_identifier: str = Query(default="", max_length=80),
    department: str = Query(default="", max_length=100),
    ward: str = Query(default="", max_length=50),
    care_status: str = Query(default="", max_length=80),
    tables: list[str] = Query(default=[]),
    limit: int = Query(default=50, ge=1, le=250),
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    try:
        return get_deterministic_lookup_service().patient_dashboard(
            user=user,
            query=q,
            patient_identifier=patient_identifier,
            department=department,
            ward=ward,
            care_status=care_status,
            tables=tables,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/admin/crm/sections")
def admin_crm_sections(
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    return get_deterministic_lookup_service().crm_sections()


@app.get("/admin/crm/{section}")
def admin_crm_list(
    section: str,
    request: Request,
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    filters = {
        key: value
        for key, value in request.query_params.items()
        if key not in {"q", "limit"} and value
    }
    try:
        return get_deterministic_lookup_service().crm_list(
            section,
            user,
            query=q,
            filters=filters,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/admin/crm/{section}")
def admin_crm_create(
    section: str,
    payload: dict[str, object],
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    try:
        result = get_deterministic_lookup_service().crm_create(section, payload)
        result["metadata_sync"] = _refresh_table_metadata_after_crm_mutation()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.patch("/admin/crm/{section}/{record_id}")
def admin_crm_update(
    section: str,
    record_id: str,
    payload: dict[str, object],
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    try:
        result = get_deterministic_lookup_service().crm_update(section, record_id, payload)
        result["metadata_sync"] = _refresh_table_metadata_after_crm_mutation()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.delete("/admin/crm/{section}/{record_id}")
def admin_crm_delete(
    section: str,
    record_id: str,
    user: HealthcareUserContext = Depends(admin_user_context),
) -> dict[str, object]:
    try:
        result = get_deterministic_lookup_service().crm_delete(section, record_id)
        result["metadata_sync"] = _refresh_table_metadata_after_crm_mutation()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: HealthcareUserContext = Depends(active_user_context)) -> ChatResponse:
    result = get_agent().answer(
        user_id=user.user_id,
        query=request.query,
        session_id=request.session_id,
        user_context=user,
        execution_mode=None,
    )
    return ChatResponse(
        session_id=result.session_id,
        answer=result.answer,
        sources=[Source(**source) for source in result.sources],
        tools_used=result.tools_used,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        trace_id=result.trace_id,
        safety=result.metadata.get("safety", {}),
        audit_event=result.metadata.get("audit_event", {}),
        performance=result.metadata.get("performance", {}),
        latency_breakdown=result.metadata.get("latency_breakdown", {}),
    )


def _answer_whatsapp_message(
    *,
    query: str,
    session_id: str,
    user_context: HealthcareUserContext,
    channel_metadata: dict[str, object],
) -> str:
    result = get_agent().answer(
        user_id=user_context.user_id,
        query=query,
        session_id=session_id,
        user_context=user_context,
        execution_mode=None,
    )
    logger.info(
        "twilio_whatsapp_chat_answered user=%s session=%s trace=%s latency_ms=%s metadata=%s",
        user_context.user_id,
        result.session_id,
        result.trace_id,
        result.latency_ms,
        channel_metadata,
    )
    return result.answer


def _send_async_whatsapp_answer(
    *,
    query: str,
    session_id: str,
    user_context: HealthcareUserContext,
    to_address: str,
    channel_metadata: dict[str, object],
) -> None:
    config = get_twilio_whatsapp_config()
    try:
        answer = _answer_whatsapp_message(
            query=query,
            session_id=session_id,
            user_context=user_context,
            channel_metadata=channel_metadata,
        )
        formatted = format_whatsapp_answer(answer, max_chars=max(500, config.max_reply_chars * 3))
        chunks = split_whatsapp_messages(formatted, max_chars=max(500, config.max_reply_chars))
        for chunk in chunks:
            send_twilio_whatsapp_message(config=config, to_address=to_address, body=chunk)
    except Exception as exc:
        logger.exception("twilio_whatsapp_async_reply_failed")
        try:
            send_twilio_whatsapp_message(
                config=config,
                to_address=to_address,
                body=f"I could not complete that request: {type(exc).__name__}. Please try the web chat.",
            )
        except Exception:
            logger.exception("twilio_whatsapp_async_error_reply_failed")


@app.post("/twilio/whatsapp/webhook")
async def twilio_whatsapp_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    config = get_twilio_whatsapp_config()
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Twilio WhatsApp integration is disabled")

    message, params = await parse_twilio_message(request)
    require_valid_twilio_request(request=request, params=params, config=config)
    if not message.body:
        return Response(
            content=twiml_message("Please send a text question for the healthcare knowledge assistant."),
            media_type="application/xml",
        )

    user_context = user_context_for_sender(config, message.from_address, message.wa_id)
    if user_context is None:
        return Response(
            content=twiml_message("This WhatsApp number is not authorised to use the healthcare knowledge assistant."),
            media_type="application/xml",
        )

    sender = message.wa_id or message.from_address
    session_id = f"whatsapp:{sender}"
    channel_metadata = {
        "channel": "twilio_whatsapp",
        "message_sid": message.message_sid,
        "from": message.from_address,
        "to": message.to_address,
        "profile_name": message.profile_name,
        "wa_id": message.wa_id,
    }

    if config.async_enabled:
        background_tasks.add_task(
            _send_async_whatsapp_answer,
            query=message.body,
            session_id=session_id,
            user_context=user_context,
            to_address=message.from_address,
            channel_metadata=channel_metadata,
        )
        return Response(
            content=twiml_message("I’m checking that now and will reply here shortly."),
            media_type="application/xml",
        )

    answer = await run_in_threadpool(
        _answer_whatsapp_message,
        query=message.body,
        session_id=session_id,
        user_context=user_context,
        channel_metadata=channel_metadata,
    )
    formatted = format_whatsapp_answer(answer, max_chars=max(500, config.max_reply_chars))
    return Response(content=twiml_message(formatted), media_type="application/xml")


@app.get("/chat/sessions", response_model=list[ChatSessionSummary])
def list_chat_sessions(user_id: str = Depends(current_user)) -> list[ChatSessionSummary]:
    sessions = get_history_repository().list_sessions(user_id)
    return [
        ChatSessionSummary(
            session_id=session.session_id,
            title=session.title,
            updated_at=session.updated_at,
        )
        for session in sessions
    ]


@app.get("/chat/sessions/{session_id}", response_model=ChatSessionDetail)
def get_chat_session(session_id: str, user_id: str = Depends(current_user)) -> ChatSessionDetail:
    messages = get_history_repository().load_messages(user_id, session_id, limit=100)
    return ChatSessionDetail(session_id=session_id, messages=[message.to_api() for message in messages])


@app.get("/documents")
def documents(user: HealthcareUserContext = Depends(active_user_context)) -> list[dict[str, object]]:
    agent = get_agent()
    return [
        _document_record_payload(document)
        for document in agent.access.filter_documents(user, get_document_store().list_documents())
    ]
