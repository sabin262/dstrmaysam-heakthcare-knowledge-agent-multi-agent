from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .aws import boto3_client
from .config import AppSettings
from .retries import retry_transient


def _records_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(right, sort_keys=True, default=str)


def _merge_manifest_records(manifest: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    existing_documents = [
        dict(item)
        for item in manifest.get("documents", [])
        if isinstance(item, dict) and item.get("key")
    ]
    existing_by_key = {str(item.get("key")): item for item in existing_documents}
    updated = 0
    skipped = 0
    for record in records:
        key = str(record.get("key") or "")
        if not key:
            continue
        current = existing_by_key.get(key)
        normalized = dict(record)
        if current is not None and _records_equal(current, normalized):
            skipped += 1
            continue
        existing_by_key[key] = normalized
        updated += 1

    ordered_keys = [str(item.get("key")) for item in existing_documents if str(item.get("key")) in existing_by_key]
    ordered_set = set(ordered_keys)
    ordered_keys.extend(key for key in existing_by_key if key not in ordered_set)
    documents = [existing_by_key[key] for key in ordered_keys]
    manifest["documents"] = documents
    manifest["total_chunks"] = sum(int(item.get("chunk_count") or 0) for item in documents)
    manifest["manifest_record_sync"] = {
        "updated": updated,
        "skipped": skipped,
        "record_count": len(records),
    }
    return {"updated": updated, "skipped": skipped, "record_count": len(records)}


@dataclass
class DocumentRecord:
    title: str
    uri: str
    key: str
    content_type: str
    metadata: dict[str, Any]
    chunk_count: int = 0
    ingestion_status: str = ""


class DocumentStore:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._s3_client: Any | None = None
        self._manifest_cache: dict[str, Any] | None = None
        self._manifest_cache_expires_at = 0.0

    @property
    def s3_client(self) -> Any:
        if self._s3_client is None:
            self._s3_client = boto3_client(self.settings, "s3")
        return self._s3_client

    def list_documents(self) -> list[DocumentRecord]:
        manifest = self._load_manifest()
        records = manifest.get("documents", []) if isinstance(manifest, dict) else []
        output: list[DocumentRecord] = []
        for record in records:
            key = str(record.get("key", ""))
            title = str(record.get("title") or key.rsplit("/", 1)[-1] or "Untitled")
            uri = str(record.get("uri") or f"s3://{self.settings.s3_bucket}/{key}")
            output.append(
                DocumentRecord(
                    title=title,
                    uri=uri,
                    key=key,
                    content_type=str(record.get("content_type", "")),
                    metadata=dict(record.get("metadata", {})),
                    chunk_count=int(record.get("chunk_count") or 0),
                    ingestion_status=str(record.get("ingestion_status") or ""),
                )
            )
        return output

    def lookup_table(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return []

    def list_raw_document_keys(self) -> list[str]:
        if not self.settings.s3_bucket:
            return []
        prefix = self.settings.s3_raw_prefix
        keys: list[str] = []
        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.settings.s3_bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = str(item.get("Key") or "")
                if key and not key.endswith("/"):
                    keys.append(key)
        return sorted(keys)

    @retry_transient
    def read_text(self, key: str) -> str:
        response = self.s3_client.get_object(Bucket=self.settings.s3_bucket, Key=key)
        data = response["Body"].read()
        return data.decode("utf-8", errors="replace")

    @retry_transient
    def upload_document(self, key: str, data: bytes, content_type: str) -> None:
        self.s3_client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        self.invalidate_manifest_cache()

    @retry_transient
    def upsert_manifest_record(self, record: dict[str, Any]) -> None:
        self.upsert_manifest_records([record])

    @retry_transient
    def upsert_manifest_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        manifest = self._load_manifest()
        result = _merge_manifest_records(manifest, records)
        if result["updated"] == 0:
            return result
        self.s3_client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=self.settings.s3_manifest_key,
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        self.invalidate_manifest_cache()
        return result

    @retry_transient
    def replace_manifest(self, manifest: dict[str, Any]) -> None:
        self.s3_client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=self.settings.s3_manifest_key,
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        self.invalidate_manifest_cache()

    def invalidate_manifest_cache(self) -> None:
        self._manifest_cache = None
        self._manifest_cache_expires_at = 0.0

    @retry_transient
    def _load_manifest(self) -> dict[str, Any]:
        if not self.settings.s3_bucket:
            return {"documents": []}
        ttl_seconds = max(0, self.settings.document_manifest_cache_ttl_seconds)
        now = time.monotonic()
        if (
            ttl_seconds
            and self._manifest_cache is not None
            and now < self._manifest_cache_expires_at
        ):
            return self._manifest_cache
        try:
            response = self.s3_client.get_object(
                Bucket=self.settings.s3_bucket, Key=self.settings.s3_manifest_key
            )
            manifest = json.loads(response["Body"].read().decode("utf-8"))
        except Exception:
            manifest = {"documents": []}
        if ttl_seconds:
            self._manifest_cache = manifest
            self._manifest_cache_expires_at = now + ttl_seconds
        return manifest


class LocalDocumentStore(DocumentStore):
    def __init__(self, settings: AppSettings):
        super().__init__(settings)
        self.local_data_dir = Path(settings.local_data_dir)

    def list_documents(self) -> list[DocumentRecord]:
        manifest = self._load_manifest()
        records = manifest.get("documents", []) if isinstance(manifest, dict) else []
        output: list[DocumentRecord] = []
        for record in records:
            key = str(record.get("key", ""))
            title = str(record.get("title") or key.rsplit("/", 1)[-1] or "Untitled")
            uri = str(record.get("uri") or f"local://{key}")
            output.append(
                DocumentRecord(
                    title=title,
                    uri=uri,
                    key=key,
                    content_type=str(record.get("content_type", "")),
                    metadata=dict(record.get("metadata", {})),
                    chunk_count=int(record.get("chunk_count") or 0),
                    ingestion_status=str(record.get("ingestion_status") or ""),
                )
            )
        return output

    def read_text(self, key: str) -> str:
        return self._path_for_key(key).read_text(encoding="utf-8", errors="replace")

    def upload_document(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.invalidate_manifest_cache()

    def list_raw_document_keys(self) -> list[str]:
        root = self._path_for_key(self.settings.s3_raw_prefix)
        if not root.exists():
            return []
        keys: list[str] = []
        for path in root.rglob("*"):
            if path.is_file():
                keys.append(path.relative_to(self.local_data_dir).as_posix())
        return sorted(keys)

    def upsert_manifest_record(self, record: dict[str, Any]) -> None:
        self.upsert_manifest_records([record])

    def upsert_manifest_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        manifest = self._load_manifest()
        result = _merge_manifest_records(manifest, records)
        if result["updated"] == 0:
            return result
        path = self._path_for_key(self.settings.s3_manifest_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.invalidate_manifest_cache()
        return result

    def replace_manifest(self, manifest: dict[str, Any]) -> None:
        path = self._path_for_key(self.settings.s3_manifest_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.invalidate_manifest_cache()

    def _load_manifest(self) -> dict[str, Any]:
        ttl_seconds = max(0, self.settings.document_manifest_cache_ttl_seconds)
        now = time.monotonic()
        if (
            ttl_seconds
            and self._manifest_cache is not None
            and now < self._manifest_cache_expires_at
        ):
            return self._manifest_cache
        path = self._path_for_key(self.settings.s3_manifest_key)
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {"documents": []}
        if ttl_seconds:
            self._manifest_cache = manifest
            self._manifest_cache_expires_at = now + ttl_seconds
        return manifest

    def _path_for_key(self, key: str) -> Path:
        safe_key = key.replace("\\", "/").lstrip("/")
        path = (self.local_data_dir / safe_key).resolve()
        root = self.local_data_dir.resolve()
        if root != path and root not in path.parents:
            raise ValueError("Local document key escapes LOCAL_DATA_DIR")
        return path
