from __future__ import annotations

import json
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .deterministic_lookup import DeterministicLookupService
from .runtime import HealthcareUserContext, user_context_from_payload


STOPWORDS = {
    "a",
    "all",
    "any",
    "anybody",
    "anyone",
    "are",
    "be",
    "does",
    "do",
    "for",
    "from",
    "have",
    "how",
    "in",
    "info",
    "information",
    "is",
    "list",
    "many",
    "me",
    "of",
    "on",
    "show",
    "tell",
    "the",
    "there",
    "to",
    "we",
    "what",
    "which",
    "who",
}
CATALOG_RESULT_LIMIT = 50
CATALOG_QUERY_STOPWORDS = STOPWORDS | {
    "available",
    "catalog",
    "catalogue",
    "document",
    "documents",
    "file",
    "files",
}
POLICY_DOMAINS = {"clinical_policy", "admin_policy", "compliance"}
POLICY_DOCUMENT_TYPES = {"policy", "sop", "pathway", "guideline"}
POLICY_TEXT_MARKERS = (
    "policy",
    "policies",
    "procedure",
    "sop",
    "guideline",
    "pathway",
    "compliance",
    "governance",
)
CATALOG_RAG_CANDIDATE_LIMIT = 8


@dataclass
class RetrievalHit:
    title: str
    uri: str
    text: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentRecord:
    title: str
    uri: str
    key: str
    content_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_count: int = 0
    ingestion_status: str = ""


@dataclass(frozen=True)
class SourceGovernance:
    owner: str = "unknown"
    version: str = "unknown"
    effective_date: str = "unknown"
    review_date: str = "unknown"
    approval_status: str = "unknown"
    sensitivity: str = "internal"
    domain: str = "general"
    document_type: str = "document"
    allowed_roles: tuple[str, ...] = ("staff",)

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "SourceGovernance":
        allowed_roles = metadata.get("allowed_roles") or metadata.get("roles") or ["staff"]
        if isinstance(allowed_roles, str):
            allowed_roles = [allowed_roles]
        return cls(
            owner=str(metadata.get("owner", "unknown")),
            version=str(metadata.get("version", "unknown")),
            effective_date=str(metadata.get("effective_date", "unknown")),
            review_date=str(metadata.get("review_date", "unknown")),
            approval_status=str(metadata.get("approval_status", "unknown")),
            sensitivity=str(metadata.get("sensitivity", "internal")),
            domain=str(metadata.get("domain", "general")),
            document_type=str(metadata.get("document_type", "document")),
            allowed_roles=tuple(str(role).lower() for role in allowed_roles),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "version": self.version,
            "effective_date": self.effective_date,
            "review_date": self.review_date,
            "approval_status": self.approval_status,
            "sensitivity": self.sensitivity,
            "domain": self.domain,
            "document_type": self.document_type,
            "allowed_roles": list(self.allowed_roles),
        }


class HealthcareAccessControl:
    def can_access_metadata(self, user: HealthcareUserContext, metadata: dict[str, Any]) -> bool:
        governance = SourceGovernance.from_metadata(metadata)
        if "admin" in user.roles:
            return True
        return bool(set(user.roles) & set(governance.allowed_roles))

    def filter_documents(self, user: HealthcareUserContext, documents: list[DocumentRecord]) -> list[DocumentRecord]:
        return [document for document in documents if self.can_access_metadata(user, document.metadata)]

    def filter_hits(self, user: HealthcareUserContext, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        return [hit for hit in hits if self.can_access_metadata(user, hit.metadata)]


@dataclass(frozen=True)
class SafetyAssessment:
    risk_level: str
    flags: tuple[str, ...] = ()
    escalation_required: bool = False
    allow_answer: bool = True
    message: str = "No safety issues detected."

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "flags": list(self.flags),
            "escalation_required": self.escalation_required,
            "allow_answer": self.allow_answer,
            "message": self.message,
        }


class HealthcareSafetyGuard:
    URGENT_TERMS = (
        "chest pain",
        "stroke",
        "sepsis",
        "suicide",
        "self harm",
        "anaphylaxis",
        "cardiac arrest",
        "unconscious",
        "not breathing",
        "overdose",
        "safeguarding",
    )
    PATIENT_SPECIFIC_TERMS = (
        "patient",
        "diagnose",
        "treat",
        "prescribe",
        "dosage",
        "symptoms",
        "lab result",
        "blood pressure",
    )
    PHI_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
        ("phone", re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")),
        ("nhs_number", re.compile(r"\b\d{3}[\s-]?\d{3}[\s-]?\d{4}\b")),
        ("medical_record_number", re.compile(r"\b(?:MRN|NHS|Patient ID)[:#\s-]*[A-Z0-9-]{5,}\b", re.IGNORECASE)),
        ("date_of_birth", re.compile(r"\b(?:DOB|date of birth)[:#\s-]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE)),
    )

    def assess(self, query: str, sources: list[dict[str, Any]] | None = None) -> SafetyAssessment:
        normalized = query.lower()
        flags: list[str] = []
        escalation_required = False
        allow_answer = True
        if any(term in normalized for term in self.URGENT_TERMS):
            flags.append("urgent_or_high_risk_clinical_term")
            escalation_required = True
        if any(term in normalized for term in self.PATIENT_SPECIFIC_TERMS):
            flags.append("patient_specific_or_clinical_advice")
        if any(pattern.search(query) for _, pattern in self.PHI_PATTERNS):
            flags.append("possible_phi_detected")
        if not sources:
            flags.append("missing_cited_sources")
            if any(flag in flags for flag in ["patient_specific_or_clinical_advice", "urgent_or_high_risk_clinical_term"]):
                allow_answer = False
        if escalation_required:
            message = (
                "Potential urgent or high-risk healthcare request. Provide approved policy "
                "citations only and direct the user to local escalation pathways."
            )
        elif not allow_answer:
            message = "Clinical or patient-specific request lacks cited approved sources."
        elif flags:
            message = "Safety guard detected issues that should be reflected in the final answer."
        else:
            message = "No safety issues detected."
        return SafetyAssessment(
            risk_level="high" if escalation_required else "medium" if flags else "low",
            flags=tuple(flags),
            escalation_required=escalation_required,
            allow_answer=allow_answer,
            message=message,
        )


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _secret_value(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        for candidate in (key, key.upper()):
            value = data.get(candidate)
            if value not in (None, ""):
                return value
    return default


def _terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9_@.+-]+", query.lower()) if term and term not in STOPWORDS]


def catalog_query_terms(query: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-z0-9_@.+-]+", query.lower())
        if term and term not in CATALOG_QUERY_STOPWORDS
    ]


def _document_record_from_any(record: Any, settings: Any | None = None) -> DocumentRecord:
    if isinstance(record, DocumentRecord):
        return record
    if isinstance(record, dict):
        key = str(record.get("key") or "")
        title = str(record.get("title") or key.rsplit("/", 1)[-1] or "Untitled")
        uri = str(record.get("uri") or _default_uri(settings, key))
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        return DocumentRecord(
            title=title,
            uri=uri,
            key=key,
            content_type=str(record.get("content_type") or ""),
            metadata=dict(metadata),
            chunk_count=int(record.get("chunk_count") or 0),
            ingestion_status=str(record.get("ingestion_status") or ""),
        )
    key = str(getattr(record, "key", "") or "")
    return DocumentRecord(
        title=str(getattr(record, "title", "") or key.rsplit("/", 1)[-1] or "Untitled"),
        uri=str(getattr(record, "uri", "") or _default_uri(settings, key)),
        key=key,
        content_type=str(getattr(record, "content_type", "") or ""),
        metadata=dict(getattr(record, "metadata", {}) or {}),
        chunk_count=int(getattr(record, "chunk_count", 0) or 0),
        ingestion_status=str(getattr(record, "ingestion_status", "") or ""),
    )


def _retrieval_hit_from_any(hit: Any) -> RetrievalHit:
    if isinstance(hit, RetrievalHit):
        return hit
    if isinstance(hit, dict):
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        return RetrievalHit(
            title=str(hit.get("title") or hit.get("key") or "Untitled"),
            uri=str(hit.get("uri") or hit.get("source") or ""),
            text=str(hit.get("text") or ""),
            score=float(hit.get("score")) if hit.get("score") is not None else None,
            metadata=dict(metadata),
        )
    return RetrievalHit(
        title=str(getattr(hit, "title", "") or "Untitled"),
        uri=str(getattr(hit, "uri", "") or ""),
        text=str(getattr(hit, "text", "") or ""),
        score=float(getattr(hit, "score")) if getattr(hit, "score", None) is not None else None,
        metadata=dict(getattr(hit, "metadata", {}) or {}),
    )


def _default_uri(settings: Any | None, key: str) -> str:
    bucket = str(_attr(settings, "s3_bucket", "") or "")
    if bucket and key:
        return f"s3://{bucket}/{key}"
    return key


def _metadata_is_policy(metadata: dict[str, Any], title: str = "", uri: str = "", key: str = "") -> bool:
    domain = str(metadata.get("domain", "")).lower()
    document_type = str(metadata.get("document_type", "")).lower()
    if domain in POLICY_DOMAINS or document_type in POLICY_DOCUMENT_TYPES:
        return True
    haystack = " ".join(
        [
            title,
            uri,
            key,
            str(metadata.get("title") or ""),
            str(metadata.get("key") or ""),
            str(metadata.get("filename") or ""),
        ]
    ).replace("_", " ").replace("-", " ").lower()
    return any(marker in haystack for marker in POLICY_TEXT_MARKERS)


def document_matches_catalog_query(record: DocumentRecord, query: str) -> bool:
    terms = catalog_query_terms(query)
    haystack = " ".join(
        [
            record.title,
            record.key,
            record.content_type,
            json.dumps(record.metadata, sort_keys=True),
        ]
    ).lower()
    return not terms or any(term in haystack for term in terms)


def document_catalog_payload(record: DocumentRecord) -> dict[str, Any]:
    governance = SourceGovernance.from_metadata(record.metadata)
    return {
        "title": record.title,
        "uri": record.uri,
        "content_type": record.content_type,
        "metadata": record.metadata,
        "governance": governance.as_dict(),
    }


def format_retrieval_hits(hits: list[RetrievalHit]) -> str:
    if not hits:
        return "No relevant document chunks found."
    lines: list[str] = []
    for index, hit in enumerate(hits, start=1):
        details = {
            key: value
            for key, value in {
                "chunk_index": hit.metadata.get("_chunk_index"),
                "domain": hit.metadata.get("domain"),
                "document_type": hit.metadata.get("document_type"),
            }.items()
            if value not in (None, "", {})
        }
        detail_text = f"\nMetadata: {json.dumps(details, sort_keys=True)}" if details else ""
        lines.append(
            f"[{index}] {hit.title} ({hit.uri}, score={hit.score}){detail_text}\n{hit.text[:1200]}"
        )
    return "\n\n".join(lines)


class HealthcareToolExecutor:
    def __init__(
        self,
        settings: Any,
        *,
        retrieval: Any | None = None,
        documents: Any | None = None,
        deterministic_lookup: Any | None = None,
        access: HealthcareAccessControl | None = None,
        safety: HealthcareSafetyGuard | None = None,
    ):
        self.settings = settings
        self.retrieval = retrieval
        self.documents = documents
        self.deterministic_lookup = deterministic_lookup
        self.access = access or HealthcareAccessControl()
        self.safety = safety or HealthcareSafetyGuard()
        self._manifest_cache: dict[str, Any] | None = None
        self._manifest_cache_expires_at = 0.0
        self._s3_client: Any | None = None
        self._opensearch: Any | None = None
        self._embedding_model: Any | None = None
        self._embedding_deployment_name = ""
        self._embedding_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self._secret_cache: dict[str, dict[str, Any]] = {}
        self.last_timing_ms: dict[str, int] = {}

    def execute(self, tool_name: str, payload: dict[str, Any]) -> str:
        query = str(payload.get("query") or "")
        user_context = payload.get("user_context") if isinstance(payload.get("user_context"), dict) else {}
        extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        return self.execute_tool(tool_name, query, user_context=user_context, extra=extra)

    def execute_tool(
        self,
        tool_name: str,
        query: str,
        *,
        user_context: HealthcareUserContext | dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        user = _coerce_user_context(user_context)
        extra = extra or {}
        canonical_tool = "catalogue_search" if tool_name == "document_catalog" else tool_name
        if canonical_tool in {"postgres_deterministic_lookup", "calendar_rota_lookup", "formulary_table_lookup", "table_lookup"}:
            return self.deterministic_lookup_tool(query, user, tool_name=canonical_tool, extra=extra)
        if canonical_tool in {"document_search", "rag_search"}:
            return self.document_search(query, user)
        if canonical_tool == "policy_search":
            return self.policy_search(query, user)
        if canonical_tool == "catalogue_search":
            return self.catalogue_search(query, user)
        if canonical_tool == "safety_guard":
            return json.dumps(self.safety.assess(query).as_dict(), indent=2)
        return f"Tool {tool_name!r} is not registered for healthcare project."

    def deterministic_lookup_tool(
        self,
        query: str,
        user: HealthcareUserContext,
        *,
        tool_name: str = "",
        extra: dict[str, Any] | None = None,
    ) -> str:
        extra = extra or {}
        table_assets = extra.get("table_assets") if isinstance(extra.get("table_assets"), list) else None
        service = self.deterministic_lookup or DeterministicLookupService(self.settings)
        try:
            result = service.lookup(query, user, limit=50, table_assets=table_assets)
            payload = json.loads(result.to_json())
            lookup_plan = payload.get("lookup_plan") if isinstance(payload.get("lookup_plan"), dict) else {}
            lookup_plan["source"] = "healthcare_tools_core"
            lookup_plan["tool_name"] = tool_name
            payload["lookup_plan"] = lookup_plan
            return json.dumps(payload, indent=2, default=str)
        except TypeError:
            result = service.lookup(query, user, limit=50, csv_assets=table_assets)
            return result.to_json()
        except Exception as exc:
            return json.dumps(
                {
                    "category": _category(query, tool_name),
                    "message": f"Deterministic lookup failed: {type(exc).__name__}: {exc}",
                    "rows": [],
                    "lookup_plan": {"source": "healthcare_tools_core", "tool_name": tool_name, "error": str(exc)},
                },
                indent=2,
                default=str,
            )

    def document_search(self, query: str, user: HealthcareUserContext) -> str:
        hits = self._search(query)
        return format_retrieval_hits(self.access.filter_hits(user, hits))

    def policy_search(self, query: str, user: HealthcareUserContext) -> str:
        hits = self._search(query)
        filtered = [
            hit
            for hit in hits
            if _metadata_is_policy(hit.metadata, title=hit.title, uri=hit.uri, key=str(hit.metadata.get("_key") or ""))
        ]
        if filtered:
            return format_retrieval_hits(self.access.filter_hits(user, filtered))
        policy_records = [
            record
            for record in self._documents()
            if self.access.can_access_metadata(user, record.metadata)
            and _metadata_is_policy(record.metadata, title=record.title, uri=record.uri, key=record.key)
            and record.chunk_count
        ]
        candidate_keys = [record.key for record in policy_records if record.key][:CATALOG_RAG_CANDIDATE_LIMIT]
        hits = self._search(query, document_keys=candidate_keys or None)
        return format_retrieval_hits(self.access.filter_hits(user, hits))

    def catalogue_search(self, query: str, user: HealthcareUserContext) -> str:
        records = self.access.filter_documents(user, self._documents())
        matches = [document_catalog_payload(record) for record in records if document_matches_catalog_query(record, query)]
        limited = matches[:CATALOG_RESULT_LIMIT]
        return json.dumps(
            {
                "kind": "document_catalog",
                "query": query,
                "total_matches": len(matches),
                "returned_count": len(limited),
                "limit": CATALOG_RESULT_LIMIT,
                "documents": limited,
            },
            indent=2,
            default=str,
        )

    def _documents(self) -> list[DocumentRecord]:
        if self.documents is not None and hasattr(self.documents, "list_documents"):
            return [_document_record_from_any(record, self.settings) for record in self.documents.list_documents()]
        return [_document_record_from_any(record, self.settings) for record in self._manifest()]

    def _search(self, query: str, document_keys: Sequence[str] | None = None) -> list[RetrievalHit]:
        started = time.perf_counter()
        if self.retrieval is not None and hasattr(self.retrieval, "search"):
            try:
                hits = self.retrieval.search(query, document_keys=document_keys or None)
            except TypeError:
                hits = self.retrieval.search(query)
            self.last_timing_ms = dict(getattr(self.retrieval, "last_timing_ms", {}) or {})
            return [_retrieval_hit_from_any(hit) for hit in hits]

        if str(_attr(self.settings, "opensearch_endpoint", "") or ""):
            hits = self._opensearch_search(query, document_keys=document_keys)
            if hits:
                return hits
        return self._raw_text_search(query, document_keys=document_keys)

    def _raw_text_search(self, query: str, document_keys: Sequence[str] | None = None) -> list[RetrievalHit]:
        wanted = set(document_keys or [])
        terms = _terms(query)
        hits: list[tuple[int, DocumentRecord, str]] = []
        for record in self._documents():
            if wanted and record.key not in wanted:
                continue
            if record.chunk_count == 0:
                continue
            text = self._raw_text(record.key)
            haystack = " ".join([record.title, record.key, json.dumps(record.metadata), text]).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                hits.append((score, record, text))
        hits.sort(key=lambda item: item[0], reverse=True)
        limit = max(1, int(_attr(self.settings, "rag_top_k", 5) or 5))
        self.last_timing_ms = {"returned_hits": min(len(hits), limit), "total_ms": 0}
        return [
            RetrievalHit(
                title=record.title,
                uri=record.uri,
                score=float(score),
                metadata=record.metadata,
                text=text,
            )
            for score, record, text in hits[:limit]
        ]

    def _manifest(self) -> list[dict[str, Any]]:
        ttl = max(0, int(_attr(self.settings, "document_manifest_cache_ttl_seconds", 0) or 0))
        now = time.monotonic()
        if ttl and self._manifest_cache is not None and now < self._manifest_cache_expires_at:
            docs = self._manifest_cache.get("documents") if isinstance(self._manifest_cache, dict) else []
            return list(docs) if isinstance(docs, list) else []
        data: dict[str, Any] = {"documents": []}
        if _uses_local_resources(self.settings):
            path = Path(str(_attr(self.settings, "local_data_dir", "local_data"))) / str(
                _attr(self.settings, "s3_manifest_key", "manifests/documents.json")
            )
            if path.exists():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    data = loaded if isinstance(loaded, dict) else data
                except Exception:
                    pass
        else:
            try:
                response = self._s3().get_object(
                    Bucket=str(_attr(self.settings, "s3_bucket", "")),
                    Key=str(_attr(self.settings, "s3_manifest_key", "manifests/documents.json")),
                )
                loaded = json.loads(response["Body"].read().decode("utf-8"))
                data = loaded if isinstance(loaded, dict) else data
            except Exception:
                pass
        if ttl:
            self._manifest_cache = data
            self._manifest_cache_expires_at = now + ttl
        docs = data.get("documents") if isinstance(data, dict) else []
        return list(docs) if isinstance(docs, list) else []

    def _raw_text(self, key: str) -> str:
        if not key:
            return ""
        if _uses_local_resources(self.settings):
            path = Path(str(_attr(self.settings, "local_data_dir", "local_data"))) / key
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""
        try:
            response = self._s3().get_object(Bucket=str(_attr(self.settings, "s3_bucket", "")), Key=key)
            data = response["Body"].read()
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _s3(self) -> Any:
        if self._s3_client is None:
            import boto3

            self._s3_client = boto3.Session(region_name=str(_attr(self.settings, "aws_region", "eu-west-2"))).client("s3")
        return self._s3_client

    def _opensearch_search(self, query: str, document_keys: Sequence[str] | None = None) -> list[RetrievalHit]:
        client = self._opensearch_client()
        result_limit = max(1, int(_attr(self.settings, "rag_top_k", 5) or 5))
        key_filter = {"terms": {"key": list(document_keys)}} if document_keys else None
        bodies: list[dict[str, Any]] = []
        vector = self._embed_query(query)
        if vector:
            knn_field: dict[str, Any] = {"vector": vector, "k": result_limit}
            if key_filter:
                knn_field["filter"] = key_filter
            bodies.append({"size": result_limit, "query": {"knn": {"embedding": knn_field}}})
        keyword_query = {"multi_match": {"query": query, "fields": ["text^2", "title^3", "key^3", "metadata.*"]}}
        query_body = {"bool": {"must": [keyword_query], "filter": [key_filter]}} if key_filter else keyword_query
        bodies.append({"size": result_limit, "query": query_body})
        raw_hits: list[RetrievalHit] = []
        for body in bodies:
            try:
                response = client.search(index=str(_attr(self.settings, "opensearch_index", "")), body=body)
            except Exception:
                continue
            raw_hits.extend(self._hits_from_opensearch_response(response))
        hits = self._merge_hits(raw_hits)[:result_limit]
        self.last_timing_ms = {"returned_hits": len(hits), "total_ms": 0}
        return hits

    def _opensearch_client(self) -> Any:
        if self._opensearch is not None:
            return self._opensearch
        from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
        import boto3

        session = boto3.Session(region_name=str(_attr(self.settings, "aws_region", "eu-west-2")))
        credentials = session.get_credentials()
        auth = AWSV4SignerAuth(credentials, str(_attr(self.settings, "aws_region", "eu-west-2")), "aoss")
        host = str(_attr(self.settings, "opensearch_endpoint", "")).replace("https://", "").replace("http://", "")
        self._opensearch = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )
        return self._opensearch

    def _embed_query(self, query: str) -> list[float] | None:
        try:
            config = self._azure_embedding_config()
            deployment = config.get("embedding_deployment") or ""
            if not config.get("endpoint") or not config.get("api_key") or not deployment:
                return None
            if self._embedding_model is None:
                from langchain_openai import AzureOpenAIEmbeddings

                self._embedding_deployment_name = deployment
                self._embedding_model = AzureOpenAIEmbeddings(
                    azure_endpoint=config["endpoint"],
                    api_key=config["api_key"],
                    api_version=config["api_version"],
                    azure_deployment=deployment,
                )
            cache_key = (" ".join(query.lower().split()), self._embedding_deployment_name)
            if int(_attr(self.settings, "rag_embedding_cache_size", 0) or 0) > 0 and cache_key in self._embedding_cache:
                vector = self._embedding_cache.pop(cache_key)
                self._embedding_cache[cache_key] = vector
                return list(vector)
            vector = list(self._embedding_model.embed_query(query))
            if int(_attr(self.settings, "rag_embedding_cache_size", 0) or 0) > 0:
                self._embedding_cache[cache_key] = vector
                while len(self._embedding_cache) > int(_attr(self.settings, "rag_embedding_cache_size", 0) or 0):
                    self._embedding_cache.popitem(last=False)
            return vector
        except Exception:
            return None

    def _azure_embedding_config(self) -> dict[str, str]:
        config = {
            "endpoint": str(os.getenv("AZURE_OPENAI_ENDPOINT") or _attr(self.settings, "azure_openai_endpoint", "") or ""),
            "api_key": str(os.getenv("AZURE_OPENAI_API_KEY") or _attr(self.settings, "azure_openai_api_key", "") or ""),
            "api_version": str(os.getenv("AZURE_OPENAI_API_VERSION") or _attr(self.settings, "azure_openai_api_version", "2024-02-01") or ""),
            "embedding_deployment": str(
                os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
                or _attr(self.settings, "azure_openai_embedding_deployment", "")
                or ""
            ),
        }
        if config["endpoint"] and config["api_key"] and config["embedding_deployment"]:
            return config
        secret_name = str(_attr(self.settings, "azure_openai_secret_name", "") or os.getenv("AZURE_OPENAI_SECRET_NAME", ""))
        if not secret_name or _uses_local_resources(self.settings):
            return config
        try:
            secret = self._secret_json(secret_name)
        except Exception:
            return config
        return {
            "endpoint": str(_secret_value(secret, "endpoint", "AZURE_OPENAI_ENDPOINT", default=config["endpoint"])),
            "api_key": str(_secret_value(secret, "api_key", "AZURE_OPENAI_API_KEY", default=config["api_key"])),
            "api_version": str(
                _secret_value(secret, "api_version", "AZURE_OPENAI_API_VERSION", default=config["api_version"])
            ),
            "embedding_deployment": str(
                _secret_value(
                    secret,
                    "embedding_deployment",
                    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
                    default=config["embedding_deployment"],
                )
            ),
        }

    def _secret_json(self, secret_name: str) -> dict[str, Any]:
        if secret_name in self._secret_cache:
            return self._secret_cache[secret_name]
        import boto3

        client = boto3.Session(region_name=str(_attr(self.settings, "aws_region", "eu-west-2"))).client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)
        payload = json.loads((response.get("SecretString") or "{}").lstrip("\ufeffÃ¯Â»Â¿"))
        secret = payload if isinstance(payload, dict) else {}
        self._secret_cache[secret_name] = secret
        return secret

    def _hits_from_opensearch_response(self, response: dict[str, Any]) -> list[RetrievalHit]:
        hits: list[RetrievalHit] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            metadata = dict(source.get("metadata", {}))
            metadata.setdefault("_key", source.get("key"))
            metadata.setdefault("_chunk_index", source.get("chunk_index"))
            metadata.setdefault("_content_type", source.get("content_type"))
            metadata.setdefault("_checksum", source.get("checksum"))
            hits.append(
                RetrievalHit(
                    title=str(source.get("title") or source.get("key") or "Untitled"),
                    uri=str(source.get("uri") or source.get("source") or ""),
                    text=str(source.get("text") or ""),
                    score=float(hit.get("_score")) if hit.get("_score") is not None else None,
                    metadata=metadata,
                )
            )
        return hits

    def _merge_hits(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        seen: set[tuple[str, str, str]] = set()
        merged: list[RetrievalHit] = []
        for hit in hits:
            key = str(hit.metadata.get("_key") or hit.uri)
            raw_chunk_index = hit.metadata.get("_chunk_index")
            chunk_index = "" if raw_chunk_index is None else str(raw_chunk_index)
            identity = (key, chunk_index, hit.text[:80])
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(hit)
        return merged


def _coerce_user_context(user_context: HealthcareUserContext | dict[str, Any] | None) -> HealthcareUserContext:
    if isinstance(user_context, HealthcareUserContext):
        return user_context
    if user_context is not None and not isinstance(user_context, dict):
        return HealthcareUserContext(
            user_id=str(getattr(user_context, "user_id", "backend-user") or "backend-user"),
            roles=tuple(str(role).lower() for role in (getattr(user_context, "roles", None) or ["staff"])),
            departments=tuple(str(department).lower() for department in (getattr(user_context, "departments", None) or [])),
            password_change_required=bool(getattr(user_context, "password_change_required", False)),
        )
    return user_context_from_payload(user_context)


def _uses_local_resources(settings: Any) -> bool:
    use_local = getattr(settings, "use_local_resources", None)
    if callable(use_local):
        try:
            return bool(use_local())
        except Exception:
            pass
    app_env = str(_attr(settings, "app_env", os.getenv("APP_ENV", "local")) or "local").lower()
    local_admin = bool(_attr(settings, "local_test_admin_enabled", False))
    return app_env in {"local", "test"} or local_admin


def _category(query: str, tool_name: str = "") -> str:
    q = query.lower()
    if tool_name in {"calendar_rota_lookup"} or any(marker in q for marker in ["on call", "on-call", "oncall", "rota"]):
        return "staff_rota"
    if tool_name == "formulary_table_lookup" or any(marker in q for marker in ["medicine", "drug", "formulary", "dose", "restricted"]):
        return "formulary"
    if any(marker in q for marker in ["patient", "appointment", "doctor", "department", "ward", "contact"]):
        return "structured_lookup"
    return "table_lookup"
