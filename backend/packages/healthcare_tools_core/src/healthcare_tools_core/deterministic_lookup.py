from __future__ import annotations

import json
import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

from .runtime import AppSettingsLike as AppSettings
from .runtime import HealthcareUserContext


def _terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9@._+-]+", query) if len(term) >= 2]


def _like(term: str) -> str:
    return f"%{term.lower()}%"


DOCTOR_ROLE_MARKERS = {
    "doctor",
    "doctors",
    "physician",
    "physicians",
    "consultant",
    "consultants",
    "registrar",
    "registrars",
    "clinician",
    "clinicians",
}

NURSE_ROLE_MARKERS = {"nurse", "nurses", "nursing"}

STAFF_ROTA_QUERY_MARKERS = {
    "available",
    "availability",
    "last",
    "month",
    "next",
    "rota",
    "schedule",
    "scheduled",
    "shift",
    "shifts",
    "oncall",
    "call",
    "on call",
    "on-call",
    "today",
    "tomorrow",
    "week",
}

AGGREGATE_QUERY_MARKERS = {
    "count",
    "counts",
    "how",
    "many",
    "number",
    "total",
    "totals",
}

ROW_VALUE_QUERY_MARKERS = {
    "asset",
    "assets",
    "available",
    "availability",
    "device",
    "devices",
    "ecg",
    "equipment",
    "equipments",
    "inventory",
    "machine",
    "machines",
    "monitor",
    "monitors",
    "oxygen",
    "pump",
    "pumps",
    "stock",
    "ventilator",
    "ventilators",
    "wheelchair",
    "wheelchairs",
}

ROW_VALUE_GENERIC_QUERY_MARKERS = {
    "asset",
    "assets",
    "available",
    "availability",
    "device",
    "devices",
    "equipment",
    "equipments",
    "inventory",
    "machine",
    "machines",
    "stock",
}

QUERY_INTENT_MARKERS = {
    "appointment",
    "appointments",
    "available",
    "availability",
    "clinic",
    "clinics",
    "clinician",
    "clinicians",
    "consultant",
    "consultants",
    "contact",
    "contacts",
    "audit",
    "audits",
    "compliance",
    "competency",
    "competencies",
    "department",
    "departments",
    "doctor",
    "doctors",
    "drug",
    "drugs",
    "email",
    "finance",
    "financial",
    "formulary",
    "future",
    "inpatient",
    "ipd",
    "located",
    "location",
    "medicine",
    "medicines",
    "number",
    "patient",
    "patients",
    "phone",
    "physician",
    "physicians",
    "restricted",
    "schedule",
    "scheduled",
    "service",
    "services",
    "training",
    "invoice",
    "invoices",
    "balance",
    "payer",
    "unit",
    "units",
    "upcoming",
    "ward",
    "wards",
}
AUTHORITATIVE_LOOKUP_CATEGORIES = {
    "patients",
    "doctors",
    "departments",
    "contacts",
    "appointments",
    "wards",
    "formulary",
    "equipment",
    "staff_rota",
    "clinic_sessions",
    "finance",
    "compliance_audits",
    "training",
}

CRM_TABLES: dict[str, dict[str, Any]] = {
    "patients": {
        "table": "patients",
        "pk": "patient_id",
        "columns": ["patient_id", "mrn", "nhs_number", "full_name", "date_of_birth", "ward_code", "department_id", "department_name", "named_consultant", "care_status", "risk_flags", "access_level"],
        "search": ["patient_id", "mrn", "nhs_number", "full_name", "department_name", "named_consultant", "care_status", "risk_flags"],
        "filters": ["department_name", "ward_code", "care_status", "access_level"],
    },
    "doctors": {
        "table": "doctors",
        "pk": "doctor_id",
        "columns": ["doctor_id", "full_name", "grade", "specialty", "department_id", "department_name", "phone", "email", "bleep", "on_call_today", "access_level"],
        "search": ["doctor_id", "full_name", "grade", "specialty", "department_name", "phone", "email", "bleep"],
        "filters": ["department_name", "specialty", "on_call_today", "access_level"],
    },
    "departments": {
        "table": "departments",
        "pk": "department_id",
        "columns": ["department_id", "department_name", "specialty_group", "location", "main_phone", "email", "service_lead", "escalation_contact", "access_level"],
        "search": ["department_id", "department_name", "specialty_group", "location", "main_phone", "email", "service_lead", "escalation_contact"],
        "filters": ["specialty_group", "access_level"],
    },
    "schedule": {
        "table": "staff_schedule",
        "pk": "schedule_id",
        "columns": ["schedule_id", "shift_date", "department_id", "department_name", "role", "staff_name", "shift_start", "shift_end", "on_call", "contact", "access_level"],
        "search": ["schedule_id", "department_name", "role", "staff_name", "contact"],
        "filters": ["department_name", "role", "on_call", "shift_date", "access_level"],
    },
    "appointments": {
        "table": "appointments",
        "pk": "appointment_id",
        "columns": ["appointment_id", "patient_mrn", "patient_name", "clinic_name", "department_id", "department_name", "appointment_date", "appointment_time", "clinician_name", "status", "referral_priority", "access_level"],
        "search": ["appointment_id", "patient_mrn", "patient_name", "clinic_name", "department_name", "clinician_name", "status", "referral_priority"],
        "filters": ["department_name", "status", "referral_priority", "appointment_date", "access_level"],
    },
    "finance": {
        "table": "finance_records",
        "pk": "finance_id",
        "columns": ["finance_id", "patient_mrn", "patient_name", "department_id", "department_name", "account_type", "payer_type", "amount_due", "amount_paid", "balance", "invoice_status", "last_invoice_date", "access_level"],
        "search": ["finance_id", "patient_mrn", "patient_name", "department_name", "account_type", "payer_type", "invoice_status"],
        "filters": ["department_name", "payer_type", "invoice_status", "access_level"],
    },
    "wards": {
        "table": "wards",
        "pk": "ward_code",
        "columns": ["ward_code", "ward_name", "department_id", "department_name", "floor", "bed_capacity", "beds_available", "nurse_in_charge", "phone", "access_level"],
        "search": ["ward_code", "ward_name", "department_name", "floor", "nurse_in_charge", "phone"],
        "filters": ["department_name", "floor", "access_level"],
    },
    "contacts": {
        "table": "organization_contacts",
        "pk": "contact_id",
        "columns": ["contact_id", "contact_type", "department_id", "department_name", "contact_name", "role", "phone", "email", "available_hours", "escalation_level", "access_level"],
        "search": ["contact_id", "contact_type", "department_name", "contact_name", "role", "phone", "email", "available_hours"],
        "filters": ["department_name", "contact_type", "role", "escalation_level", "access_level"],
    },
    "formulary": {
        "table": "formulary",
        "pk": "medicine_id",
        "columns": ["medicine_id", "medicine_name", "category", "restricted", "approval_required", "max_adult_dose", "monitoring_required", "access_level"],
        "search": ["medicine_id", "medicine_name", "category", "approval_required", "max_adult_dose", "monitoring_required"],
        "filters": ["category", "restricted", "access_level"],
    },
    "clinic_sessions": {
        "table": "clinic_sessions",
        "pk": "clinic_id",
        "columns": ["clinic_id", "clinic_name", "clinic_date", "start_time", "consultant", "slots_total", "slots_available", "referral_priority", "access_level"],
        "search": ["clinic_id", "clinic_name", "consultant", "referral_priority"],
        "filters": ["clinic_date", "referral_priority", "access_level"],
    },
    "equipment": {
        "table": "equipment_assets",
        "pk": "asset_id",
        "columns": ["asset_id", "equipment_type", "location", "status", "last_service_date", "next_service_due", "clinical_engineering_contact", "access_level"],
        "search": ["asset_id", "equipment_type", "location", "status", "clinical_engineering_contact"],
        "filters": ["equipment_type", "location", "status", "access_level"],
    },
    "compliance_audits": {
        "table": "compliance_audits",
        "pk": "audit_id",
        "columns": ["audit_id", "department_id", "department_name", "topic", "lead", "due_date", "status", "last_score_percent", "access_level"],
        "search": ["audit_id", "department_name", "topic", "lead", "status"],
        "filters": ["department_name", "topic", "status", "access_level"],
    },
    "training": {
        "table": "training_records",
        "pk": "training_id",
        "columns": ["training_id", "staff_name", "role", "department_id", "department_name", "training_module", "completion_date", "expiry_date", "status", "access_level"],
        "search": ["training_id", "staff_name", "role", "department_name", "training_module", "status"],
        "filters": ["department_name", "training_module", "status", "access_level"],
    },
}

CSV_SEMANTIC_SAMPLE_ROWS = 200
CSV_SEMANTIC_TERM_LIMIT = 120
CSV_CATEGORICAL_COLUMN_LIMIT = 12
CSV_CATEGORICAL_VALUE_LIMIT = 20
CSV_SAMPLE_VALUE_LIMIT = 60
ROW_VALUE_CONTEXT_STOPWORDS = {
    "hospital",
    "hospitals",
    "trust",
}

BASE_STOPWORDS = {
    "show",
    "is",
    "are",
    "am",
    "be",
    "being",
    "been",
    "in",
    "on",
    "at",
    "to",
    "from",
    "of",
    "a",
    "an",
    "all",
    "anybody",
    "anyone",
    "every",
    "last",
    "month",
    "next",
    "somebody",
    "someone",
    "this",
    "what",
    "which",
    "who",
    "week",
    "previous",
    "does",
    "do",
    "did",
    "has",
    "have",
    "had",
    "any",
    "if",
    "whether",
    "tell",
    "me",
    "our",
    "list",
    "there",
    "us",
    "we",
    "where",
    "when",
    "for",
    "the",
    "and",
    "with",
    "details",
    "detail",
    "information",
    "info",
}


STOPWORDS = BASE_STOPWORDS


def _term_variants(term: str) -> set[str]:
    cleaned = term.strip().lower()
    if len(cleaned) < 2:
        return set()
    variants = {cleaned}
    if cleaned.startswith("pediatric"):
        variants.add(cleaned.replace("pediatric", "paediatric", 1))
    if cleaned.startswith("paediatric"):
        variants.add(cleaned.replace("paediatric", "pediatric", 1))
    if cleaned.endswith("ies") and len(cleaned) > 3:
        variants.add(cleaned[:-3] + "y")
    elif cleaned.endswith("s") and len(cleaned) > 3:
        variants.add(cleaned[:-1])
    else:
        variants.add(cleaned + "s")
    return {variant for variant in variants if len(variant) >= 2}


def _normalized_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for term in _terms(text):
        if term in STOPWORDS or term in AGGREGATE_QUERY_MARKERS:
            continue
        terms.update(_term_variants(term))
    return terms


def build_csv_semantic_metadata(filename: str, data: bytes) -> dict[str, Any]:
    decoded = data.decode("utf-8-sig", errors="replace")
    try:
        reader = csv.DictReader(io.StringIO(decoded))
        columns = [str(column).strip() for column in (reader.fieldnames or []) if str(column).strip()]
    except Exception:
        return {
            "columns": [],
            "semantic_terms": sorted(_normalized_terms(filename))[:CSV_SEMANTIC_TERM_LIMIT],
            "categorical_values": {},
            "sample_values": [],
        }

    semantic_terms = set(_normalized_terms(filename))
    for column in columns:
        semantic_terms.update(_normalized_terms(column))

    column_values: dict[str, set[str]] = {column: set() for column in columns}
    sample_values: list[str] = []
    seen_samples: set[str] = set()
    for index, row in enumerate(reader):
        if index >= CSV_SEMANTIC_SAMPLE_ROWS:
            break
        for column in columns:
            raw_value = row.get(column)
            value = str(raw_value).strip() if raw_value is not None else ""
            if not value:
                continue
            semantic_terms.update(_normalized_terms(value))
            if len(value) <= 80:
                column_values[column].add(value)
                sample = f"{column}={value}"
                if sample not in seen_samples and len(sample_values) < CSV_SAMPLE_VALUE_LIMIT:
                    seen_samples.add(sample)
                    sample_values.append(sample)

    categorical_values: dict[str, list[str]] = {}
    for column, values in column_values.items():
        if not values:
            continue
        if len(categorical_values) >= CSV_CATEGORICAL_COLUMN_LIMIT:
            break
        ordered_values = sorted(values, key=lambda item: (len(item), item.lower()))[:CSV_CATEGORICAL_VALUE_LIMIT]
        categorical_values[column] = ordered_values

    return {
        "columns": columns,
        "semantic_terms": sorted(semantic_terms)[:CSV_SEMANTIC_TERM_LIMIT],
        "categorical_values": categorical_values,
        "sample_values": sample_values,
    }


def build_table_semantic_metadata(
    table_key: str,
    table_name: str,
    columns: Sequence[str],
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    semantic_terms = set(_normalized_terms(" ".join([table_key, table_name, table_name.replace("_", " ")])))
    for column in columns:
        semantic_terms.update(_normalized_terms(column))
        semantic_terms.update(_normalized_terms(str(column).replace("_", " ")))

    column_values: dict[str, set[str]] = {str(column): set() for column in columns}
    sample_values: list[str] = []
    seen_samples: set[str] = set()
    for row in rows[:CSV_SEMANTIC_SAMPLE_ROWS]:
        for column in columns:
            raw_value = row.get(str(column))
            value = str(raw_value).strip() if raw_value is not None else ""
            if not value:
                continue
            semantic_terms.update(_normalized_terms(value))
            if len(value) <= 80:
                column_values[str(column)].add(value)
                sample = f"{column}={value}"
                if sample not in seen_samples and len(sample_values) < CSV_SAMPLE_VALUE_LIMIT:
                    seen_samples.add(sample)
                    sample_values.append(sample)

    categorical_values: dict[str, list[str]] = {}
    for column, values in column_values.items():
        if not values:
            continue
        if len(categorical_values) >= CSV_CATEGORICAL_COLUMN_LIMIT:
            break
        categorical_values[column] = sorted(values, key=lambda item: (len(item), item.lower()))[:CSV_CATEGORICAL_VALUE_LIMIT]

    return {
        "columns": [str(column) for column in columns],
        "semantic_terms": sorted(semantic_terms)[:CSV_SEMANTIC_TERM_LIMIT],
        "categorical_values": categorical_values,
        "sample_values": sample_values,
    }


def _best_search_term(terms: list[str], stopwords: set[str] | None = None) -> str:
    for term in terms:
        if re.fullmatch(r"(mrn)?\d{4,}|mrn\d+", term.lower()):
            return term
    non_value_terms = STOPWORDS | QUERY_INTENT_MARKERS | (stopwords or set())
    useful = [term for term in terms if term.lower() not in non_value_terms]
    return useful[-1] if useful else ""


def _has_person_name_hint(terms: list[str]) -> bool:
    non_name_markers = QUERY_INTENT_MARKERS | DOCTOR_ROLE_MARKERS | NURSE_ROLE_MARKERS | STAFF_ROTA_QUERY_MARKERS
    useful = [
        term
        for term in terms
        if term.lower() not in STOPWORDS
        and term.lower() not in non_name_markers
        and not re.fullmatch(r"(w\d+|dep-[a-z0-9-]+|\d+)", term.lower())
    ]
    name_like_terms = [term for term in useful if re.fullmatch(r"[a-z][a-z'-]+", term.lower())]
    return len(name_like_terms) >= 2


def _name_search_terms(terms: list[str], stopwords: set[str] | None = None) -> list[str]:
    non_name_terms = STOPWORDS | QUERY_INTENT_MARKERS | (stopwords or set())
    useful = [
        term.lower()
        for term in terms
        if term.lower() not in non_name_terms
        and not re.fullmatch(r"(w\d+|dep-[a-z0-9-]+|\d+)", term.lower())
    ]
    return [term for term in useful if re.fullmatch(r"[a-z][a-z'-]+", term)]


def _is_explicit_patient_lookup(query: str) -> bool:
    q = query.lower()
    if not any(marker in q for marker in ("patient", "mrn", "nhs number", "nhs_number")):
        return False
    terms = _terms(query)
    if any(re.fullmatch(r"(mrn)?\d{4,}|mrn\d+", term.lower()) for term in terms):
        return True
    return _has_person_name_hint(terms)


def _has_count_intent(query: str) -> bool:
    q = query.lower()
    terms = set(_terms(query))
    explicit_count_terms = AGGREGATE_QUERY_MARKERS - {"how"}
    return "how many" in q or "how much" in q or bool(terms & explicit_count_terms)


def _has_row_value_intent(query: str) -> bool:
    return bool(set(_terms(query)) & ROW_VALUE_QUERY_MARKERS)


def _row_value_lookup_stopwords(query: str, base_stopwords: set[str] | None = None) -> set[str]:
    base = set(base_stopwords or set())
    candidate_stopwords = base | ROW_VALUE_GENERIC_QUERY_MARKERS
    return candidate_stopwords if _expanded_search_terms(query, candidate_stopwords) else base


def _expanded_search_terms(query: str, stopwords: set[str] | None = None) -> list[str]:
    active_stopwords = STOPWORDS | AGGREGATE_QUERY_MARKERS | (stopwords or set())
    expanded: list[str] = []
    seen: set[str] = set()
    for term in _terms(query):
        if term.lower() in active_stopwords:
            continue
        for variant in sorted(_term_variants(term)):
            if variant not in active_stopwords and variant not in seen:
                seen.add(variant)
                expanded.append(variant)
    return expanded


def _tsquery(terms: Sequence[str]) -> str:
    safe_terms = [term for term in terms if re.fullmatch(r"[a-z0-9_@.+-]+", term)]
    return " | ".join(f"{term}:*" for term in safe_terms)


def _row_text(row: dict[str, Any]) -> str:
    return (
        json.dumps(row.get("row") or {}, sort_keys=True, default=str).lower()
        + " "
        + str(row.get("source_table") or "").lower()
        + " "
        + str(row.get("source_filename") or "").lower()
    )


def _matched_terms(terms: Sequence[str], rows: Sequence[dict[str, Any]]) -> list[str]:
    matched: list[str] = []
    for term in terms:
        if any(term in _row_text(row) for row in rows):
            matched.append(term)
    return matched


def _matched_columns(terms: Sequence[str], rows: Sequence[dict[str, Any]]) -> list[str]:
    columns: set[str] = set()
    for row in rows:
        payload = row.get("row") if isinstance(row, dict) else {}
        if not isinstance(payload, dict):
            continue
        for column, value in payload.items():
            haystack = f"{column} {value}".lower()
            if any(term in haystack for term in terms):
                columns.add(str(column))
    return sorted(columns)


def _strict_row_value_term_groups(query: str, stopwords: set[str] | None = None) -> list[set[str]]:
    active_stopwords = STOPWORDS | AGGREGATE_QUERY_MARKERS | ROW_VALUE_CONTEXT_STOPWORDS | (stopwords or set())
    groups: list[set[str]] = []
    seen: set[str] = set()
    for term in _terms(query):
        if term in active_stopwords:
            continue
        variants = _term_variants(term) - active_stopwords
        if not variants:
            continue
        key = "|".join(sorted(variants))
        if key in seen:
            continue
        seen.add(key)
        groups.append(variants)
    return groups


def _row_matches_term_groups(row: dict[str, Any], term_groups: Sequence[set[str]]) -> bool:
    text = _row_text(row)
    return all(any(term in text for term in group) for group in term_groups)


def _filter_rows_for_specific_row_values(
    query: str,
    rows: Sequence[dict[str, Any]],
    stopwords: set[str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    term_groups = _strict_row_value_term_groups(query, stopwords)
    if not term_groups:
        return list(rows), False
    table_rows = [row for row in rows if isinstance(row, dict) and row.get("source_table")]
    if not table_rows:
        return list(rows), False
    strict_rows = [row for row in table_rows if _row_matches_term_groups(row, term_groups)]
    if strict_rows:
        return strict_rows, True
    return list(rows), False


def _counts_by_source(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source_table") or "")
        if source == "uploaded_lookup_rows":
            source = str(row.get("source_filename") or source)
        if not source:
            continue
        counts[source] = counts.get(source, 0) + 1
    return counts


def _source_tables(rows: Sequence[dict[str, Any]]) -> list[str]:
    sources: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source_table") or "").strip()
        if source == "uploaded_lookup_rows":
            source = str(row.get("source_filename") or source).strip()
        if source:
            sources.add(source)
    return sorted(sources)


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _generated_id(prefix: str, *values: Any) -> str:
    raw = "-".join(str(value).strip().lower() for value in values if str(value).strip())
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if not cleaned:
        cleaned = "record"
    return f"{prefix}-{cleaned[:48]}".upper()


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _department_id_for_name(name: str) -> str | None:
    normalized = str(name).strip().lower()
    mapping = {
        "cardiology": "DEP-CARD",
        "community care": "DEP-COMM",
        "emergency department": "DEP-ED",
        "icu": "DEP-ICU",
        "intensive care unit": "DEP-ICU",
        "maternity": "DEP-MAT",
        "mental health": "DEP-MH",
        "oncology": "DEP-ONC",
        "paediatrics": "DEP-PAED",
        "pathology": "DEP-PATH",
        "pharmacy": "DEP-PHAR",
        "radiology": "DEP-RAD",
        "renal": "DEP-RENAL",
        "respiratory": "DEP-RESP",
        "surgery": "DEP-SURG",
    }
    return mapping.get(normalized)


def _row_value(payload: dict[str, Any], field_candidates: Sequence[str]) -> Any:
    candidate_keys = {_normalized_key(field) for field in field_candidates}
    for key, value in payload.items():
        if value in (None, "", []):
            continue
        if _normalized_key(str(key)) in candidate_keys:
            return value
    return None


def _has_list_intent(query: str) -> bool:
    terms = set(_terms(query))
    return bool(terms & {"all", "available", "every", "list", "show"})


def _is_equipment_asset_list_query(query: str) -> bool:
    q = query.lower()
    if not _has_list_intent(query):
        return False
    terms = set(_terms(query))
    if terms & {"equipment", "equipments", "asset", "assets", "device", "devices"}:
        return True
    return any(
        marker in q
        for marker in (
            "equipment type",
            "equipment types",
            "asset type",
            "asset types",
            "device type",
            "device types",
        )
    )


def _is_medicine_list_query(query: str) -> bool:
    if not _has_list_intent(query):
        return False
    terms = set(_terms(query))
    return bool(terms & {"medicine", "medicines", "medication", "medications", "drug", "drugs", "formulary"})


def _has_generic_info_intent(query: str) -> bool:
    q = query.lower().strip()
    return bool(
        re.search(r"\b(info|information|details?|detail|facts?)\s+(on|about|for)\b", q)
        or re.search(r"\bwhat\s+is\b", q)
    )


def _row_matches_query_entity(row: dict[str, Any], query: str, fields: Sequence[str]) -> bool:
    query_terms = {
        term
        for term in _expanded_search_terms(query, QUERY_INTENT_MARKERS | ROW_VALUE_CONTEXT_STOPWORDS)
        if len(term) > 2
    }
    if not query_terms:
        return False
    for field in fields:
        value = str((row.get("row") or row).get(field) or "").lower()
        if not value:
            continue
        value_terms = set(_terms(value))
        if query_terms & value_terms:
            return True
        if any(term in value for term in query_terms):
            return True
    return False


def _requested_rota_dates(query: str, today: date | None = None) -> list[str]:
    q = query.lower()
    base_date = today or date.today()
    requested: list[date] = []
    if "today" in q:
        requested.append(base_date)
    if "tomorrow" in q:
        requested.append(base_date + timedelta(days=1))
    if "yesterday" in q:
        requested.append(base_date - timedelta(days=1))
    week_start = base_date - timedelta(days=base_date.weekday())
    if "next week" in q:
        requested.extend(week_start + timedelta(days=offset) for offset in range(7, 14))
    elif "last week" in q or "previous week" in q:
        requested.extend(week_start + timedelta(days=offset) for offset in range(-7, 0))
    elif "this week" in q:
        requested.extend(week_start + timedelta(days=offset) for offset in range(7))

    def month_range(year: int, month: int) -> list[date]:
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        first_day = date(year, month, 1)
        days = (next_month - first_day).days
        return [first_day + timedelta(days=offset) for offset in range(days)]

    if "next month" in q:
        year = base_date.year + (1 if base_date.month == 12 else 0)
        month = 1 if base_date.month == 12 else base_date.month + 1
        requested.extend(month_range(year, month))
    elif "last month" in q or "previous month" in q:
        year = base_date.year - (1 if base_date.month == 1 else 0)
        month = 12 if base_date.month == 1 else base_date.month - 1
        requested.extend(month_range(year, month))
    elif "this month" in q or re.search(r"\bmonth\b", q):
        requested.extend(month_range(base_date.year, base_date.month))
    for match in re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", query):
        try:
            requested.append(date.fromisoformat(match))
        except ValueError:
            continue
    if not requested and any(marker in q for marker in ["available", "availability", "rota", "schedule", "scheduled", "shift"]):
        requested.append(base_date)

    unique: list[str] = []
    for value in requested:
        iso_value = value.isoformat()
        if iso_value not in unique:
            unique.append(iso_value)
    return unique


def _resolved_today() -> str:
    return date.today().isoformat()


def _requested_rota_role_groups(query: str) -> set[str]:
    terms = set(_terms(query))
    groups: set[str] = set()
    if terms & DOCTOR_ROLE_MARKERS:
        groups.add("doctor")
    if terms & NURSE_ROLE_MARKERS:
        groups.add("nurse")
    return groups


def _is_staff_rota_query(query: str) -> bool:
    q = query.lower()
    terms = set(_terms(query))
    role_requested = bool(terms & (DOCTOR_ROLE_MARKERS | NURSE_ROLE_MARKERS))
    rota_requested = any(marker in q for marker in STAFF_ROTA_QUERY_MARKERS)
    generic_on_call_requested = bool(terms & {"anybody", "anyone", "who"}) and any(
        marker in q for marker in ["on call", "on-call", "oncall"]
    )
    dated_on_call_requested = any(marker in q for marker in ["on call", "on-call", "oncall"]) and any(
        marker in q
        for marker in [
            "today",
            "tomorrow",
            "yesterday",
            "this week",
            "next week",
            "last week",
            "previous week",
            "this month",
            "next month",
            "last month",
            "previous month",
        ]
    )
    mentions_staff_rota = "staff_rota" in q or "staff rota" in q
    return mentions_staff_rota or generic_on_call_requested or dated_on_call_requested or (role_requested and rota_requested)


def _staff_rota_query_focus(query: str) -> str:
    """Return the rota-specific clause from a multipart question."""
    q = str(query or "").strip()
    if not q:
        return q
    parts = [part.strip(" .?") for part in re.split(r"\s*[;?]\s*|\b(?:and|also|plus)\b", q, flags=re.IGNORECASE)]
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return q

    date_only_terms = {
        "today",
        "tomorrow",
        "yesterday",
        "this week",
        "next week",
        "last week",
        "previous week",
        "this month",
        "next month",
        "last month",
        "previous month",
    }
    tail_parts = parts[1:]
    if tail_parts and all(part.lower() in date_only_terms for part in tail_parts):
        return q

    for part in parts:
        lowered = part.lower()
        if (
            "staff_rota" in lowered
            or "staff rota" in lowered
            or any(marker in lowered for marker in ("on call", "on-call", "oncall", "rota", "schedule", "shift"))
        ):
            return part
    return q


def _requires_on_call(query: str) -> bool:
    q = query.lower()
    return any(marker in q for marker in ["on call", "on-call", "oncall", "available", "availability"])


def _is_rota_csv_asset(asset: dict[str, Any]) -> bool:
    filename = str(asset.get("filename") or asset.get("title") or "").lower()
    if any(marker in filename for marker in ["rota", "oncall", "on_call", "on-call"]):
        return True
    columns = {str(column).lower() for column in asset.get("columns") or []}
    has_date_or_shift = bool(columns & {"date", "shift_date", "day", "shift_start", "shift_end"})
    has_staff_identity = bool(columns & {"staff_name", "doctor", "nurse", "clinician", "name", "role"})
    has_rota_state = bool(columns & {"on_call", "status", "shift", "shift_start", "shift_end"})
    return has_date_or_shift and has_staff_identity and has_rota_state


def _rota_csv_filenames(
    query: str,
    csv_assets: Sequence[dict[str, Any]],
    selected_filenames: Sequence[str],
) -> list[str]:
    if not _is_staff_rota_query(query):
        return []
    filenames: list[str] = []
    selected = {str(filename) for filename in selected_filenames if filename}
    for asset in csv_assets:
        if not _is_rota_csv_asset(asset):
            continue
        filename = str(asset.get("filename") or asset.get("title") or asset.get("table_name") or "")
        if filename and (filename in selected or not selected) and filename not in filenames:
            filenames.append(filename)
    if not filenames:
        for asset in csv_assets:
            if _is_rota_csv_asset(asset):
                filename = str(asset.get("filename") or asset.get("title") or asset.get("table_name") or "")
                if filename and filename not in filenames:
                    filenames.append(filename)
    return filenames


def _access_scopes(user: HealthcareUserContext) -> tuple[str, ...]:
    roles = set(user.roles)
    if "admin" in roles or "director" in roles:
        return ("all_staff", "clinical", "pharmacy", "manager", "hr_manager", "ig_manager", "director")
    scopes = {"all_staff"}
    if roles & {"doctor", "physician", "nurse", "clinical", "clinician"}:
        scopes.add("clinical")
    if roles & {"pharmacist", "pharmacy"}:
        scopes.update({"clinical", "pharmacy"})
    if roles & {"manager", "department_manager"}:
        scopes.update({"clinical", "manager"})
    if roles & {"hr", "hr_manager"}:
        scopes.add("hr_manager")
    if roles & {"ig_manager", "information_governance"}:
        scopes.add("ig_manager")
    return tuple(sorted(scopes))


def _staff_rota_access_scopes(scopes: Sequence[str]) -> tuple[str, ...]:
    expanded = set(scopes)
    if "all_staff" in expanded:
        expanded.update({"clinical", "manager"})
    return tuple(sorted(expanded))


@dataclass(frozen=True)
class LookupResult:
    category: str
    rows: list[dict[str, Any]]
    access_scopes: tuple[str, ...]
    message: str = ""
    lookup_plan: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "category": self.category,
                "message": self.message,
                "access_scopes_applied": list(self.access_scopes),
                "lookup_plan": self.lookup_plan,
                "rows": self.rows,
            },
            indent=2,
            default=str,
        )


@dataclass(frozen=True)
class CsvTableSyncResult:
    filename: str
    table_key: str
    table_name: str
    rows_inserted: int
    columns: list[str]
    semantic_metadata: dict[str, Any]

    def to_manifest_metadata(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "table_key": self.table_key,
            "table_name": self.table_name,
            "rows_inserted": self.rows_inserted,
            "columns": self.columns,
            "semantic_metadata": self.semantic_metadata,
        }


class UnsupportedCsvLookupError(ValueError):
    def __init__(self, filename: str, columns: Sequence[str]):
        self.filename = filename
        self.columns = [str(column) for column in columns]
        super().__init__(
            "Unsupported CSV lookup upload. Supported CSVs must match one of: "
            + ", ".join(sorted(CSV_TABLE_MAPPINGS))
            + f". Received {filename} with columns: "
            + (", ".join(self.columns) if self.columns else "none")
        )


CSV_TABLE_MAPPINGS: dict[str, dict[str, Any]] = {
    "staff_rota.csv": {
        "table_key": "schedule",
        "required_any": ({"date", "shift_date"}, {"staff_name", "name"}, {"department"}, {"role"}),
    },
    "doctor_rota.csv": {
        "table_key": "schedule",
        "required_any": ({"date", "shift_date"}, {"doctor", "clinician", "staff_name", "name"}),
    },
    "appointment_clinics.csv": {
        "table_key": "clinic_sessions",
        "required_any": ({"clinic_id"}, {"clinic_name"}, {"date", "clinic_date"}, {"consultant"}),
    },
    "equipment_assets.csv": {
        "table_key": "equipment",
        "required_any": ({"asset_id"}, {"equipment_type"}, {"location"}, {"status"}),
    },
    "medication_formulary.csv": {
        "table_key": "formulary",
        "required_any": ({"medicine", "medicine_name", "drug"}, {"category"}),
    },
    "ward_directory.csv": {
        "table_key": "wards",
        "required_any": ({"ward_code"}, {"ward_name"}, {"specialty", "department"}),
    },
    "department_contacts.csv": {
        "table_key": "contacts",
        "required_any": ({"contact_name"}, {"department"}, {"role"}, {"phone", "email"}),
    },
    "audit_schedule.csv": {
        "table_key": "compliance_audits",
        "required_any": ({"audit_id"}, {"topic"}, {"department"}, {"due_date"}),
    },
    "training_compliance.csv": {
        "table_key": "training",
        "required_any": ({"staff_name"}, {"training_module"}, {"department"}, {"status"}),
    },
}


def _normalized_columns(columns: Sequence[str]) -> set[str]:
    return {_normalized_key(str(column)) for column in columns if str(column).strip()}


def supported_csv_lookup_mappings() -> dict[str, dict[str, Any]]:
    return {
        filename: {
            "table_key": str(config["table_key"]),
            "table_name": CRM_TABLES[str(config["table_key"])]["table"],
            "required_any": [sorted(group) for group in config["required_any"]],
        }
        for filename, config in CSV_TABLE_MAPPINGS.items()
    }


def detect_csv_table_mapping(filename: str, columns: Sequence[str]) -> dict[str, Any] | None:
    normalized_filename = filename.lower()
    normalized_columns = _normalized_columns(columns)
    candidates = []
    if normalized_filename in CSV_TABLE_MAPPINGS:
        candidates.append(CSV_TABLE_MAPPINGS[normalized_filename])
    candidates.extend(config for key, config in CSV_TABLE_MAPPINGS.items() if key != normalized_filename)
    for config in candidates:
        if all(normalized_columns & {_normalized_key(column) for column in group} for group in config["required_any"]):
            table_key = str(config["table_key"])
            return {
                **config,
                "table_key": table_key,
                "table_name": CRM_TABLES[table_key]["table"],
            }
    return None


class DeterministicLookupService:
    """Safe Postgres lookup service for exact operational healthcare data."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    def table_lookup_manifest_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with self._connect() as conn:
            with conn.cursor() as cur:
                for table_key, config in CRM_TABLES.items():
                    table_name = str(config["table"])
                    columns = [str(column) for column in config["columns"]]
                    selected_columns = ", ".join(columns)
                    cur.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}")
                    count_row = cur.fetchone() or {}
                    row_count = int(count_row.get("row_count") or 0)
                    cur.execute(
                        f"""
                        SELECT {selected_columns}
                        FROM {table_name}
                        ORDER BY {config["pk"]}
                        LIMIT %s
                        """,
                        (CSV_SEMANTIC_SAMPLE_ROWS,),
                    )
                    sample_rows = [dict(row) for row in cur.fetchall()]
                    semantic_metadata = build_table_semantic_metadata(table_key, table_name, columns, sample_rows)
                    lookup_uri = f"postgres://table/{table_name}"
                    title = f"{table_key.replace('_', ' ').title()} table"
                    checksum_payload = {
                        "table_key": table_key,
                        "table_name": table_name,
                        "row_count": row_count,
                        "columns": columns,
                        "semantic_metadata": semantic_metadata,
                    }
                    checksum = hashlib.sha256(
                        json.dumps(checksum_payload, sort_keys=True, default=str).encode("utf-8")
                    ).hexdigest()
                    records.append(
                        {
                            "key": lookup_uri,
                            "title": title,
                            "uri": lookup_uri,
                            "content_type": "application/vnd.postgresql.table+json",
                            "checksum": checksum,
                            "metadata": {
                                "key": lookup_uri,
                                "checksum": checksum,
                                "owner": "system",
                                "version": "postgres",
                                "effective_date": "system",
                                "review_date": "system",
                                "approval_status": "system",
                                "sensitivity": "internal",
                                "domain": "deterministic_lookup",
                                "document_type": "postgres_table",
                                "allowed_roles": [
                                    "staff",
                                    "admin",
                                    "manager",
                                    "doctor",
                                    "nurse",
                                    "pharmacy",
                                    "clinical_governance",
                                ],
                                "asset_source": "postgres_table_lookup",
                                "source_table": table_name,
                                "source_table_key": table_key,
                                "lookup_uri": lookup_uri,
                                "row_count": row_count,
                                "columns": columns,
                                "semantic_terms": semantic_metadata.get("semantic_terms") or [],
                                "categorical_values": semantic_metadata.get("categorical_values") or {},
                                "sample_values": semantic_metadata.get("sample_values") or [],
                                "search_backend": "postgres",
                                "rag_indexed": False,
                            },
                            "chunk_count": 0,
                            "ingestion_status": "metadata_only",
                        }
                    )
        return records

    def lookup(
        self,
        query: str,
        user: HealthcareUserContext,
        limit: int = 10,
        table_assets: Sequence[dict[str, Any]] | None = None,
        csv_assets: Sequence[dict[str, Any]] | None = None,
    ) -> LookupResult:
        if not self.settings.deterministic_lookup_enabled:
            return LookupResult("disabled", [], _access_scopes(user), "Deterministic lookup is disabled.")

        category = self._classify(query)
        scopes = _access_scopes(user)
        lookup_stopwords: set[str] = set()
        search_terms = self._search_terms(query, lookup_stopwords)
        selected_assets = self._matching_table_assets(query, table_assets or csv_assets or [])
        selected_tables = [
            str(asset.get("filename") or asset.get("table_name") or "")
            for asset in selected_assets
            if asset.get("filename") or asset.get("table_name")
        ]
        aggregate_intent = "count" if _has_count_intent(query) else ""
        row_value_count_stopwords = (
            _row_value_lookup_stopwords(query, lookup_stopwords)
            if aggregate_intent == "count" and _has_row_value_intent(query)
            else lookup_stopwords
        )
        aggregate_result: dict[str, Any] | None = None
        resolved_today = _resolved_today()
        requested_rota_dates: list[str] = []
        row_value_search_used = False
        strict_row_value_filter_applied = False
        matched_table_sources: list[str] = []
        matched_terms: list[str] = []
        matched_columns: list[str] = []
        distinct_field = ""
        authoritative_patient_lookup = category == "patients" and _is_explicit_patient_lookup(query)
        category_first = (
            category in AUTHORITATIVE_LOOKUP_CATEGORIES
            and aggregate_intent != "count"
            and not _has_row_value_intent(query)
        )
        authoritative_list_query = category in AUTHORITATIVE_LOOKUP_CATEGORIES and _has_list_intent(query)
        try:
            handled_distinct_lookup = False
            if category == "equipment" and _is_equipment_asset_list_query(query):
                distinct_field = "equipment_type"
                try:
                    rows = self._query_equipment_distinct_values(scopes, limit)
                except Exception:
                    rows = []
                if not rows:
                    rows = []
                if rows:
                    row_value_search_used = True
                    handled_distinct_lookup = True
                    matched_table_sources = ["equipment_assets"]
            elif category == "equipment":
                try:
                    with self._connect() as conn:
                        with conn.cursor() as cur:
                            rows = self._query_equipment(cur, _terms(query), scopes, limit, row_value_count_stopwords)
                except Exception:
                    rows = []
                if aggregate_intent == "count":
                    try:
                        matching_rows = self._count_equipment(query, scopes, stopwords=row_value_count_stopwords)
                    except Exception:
                        matching_rows = 0
                    aggregate_result = {
                        "type": "count",
                        "matching_rows": matching_rows,
                        "counts_by_source": {"equipment_assets": matching_rows},
                        "source_tables": ["equipment_assets"],
                    }
                if rows:
                    matched_table_sources = ["equipment_assets"]
                    handled_distinct_lookup = True
                else:
                    rows = []
            elif _is_medicine_list_query(query):
                distinct_field = "medicine"
                try:
                    rows = self._query_formulary_distinct_values(scopes, limit)
                except Exception:
                    rows = []
                if rows:
                    row_value_search_used = True
                    handled_distinct_lookup = True
                    matched_table_sources = ["formulary"]

            if handled_distinct_lookup:
                pass
            elif _is_staff_rota_query(query):
                rota_query = _staff_rota_query_focus(query)
                requested_rota_dates = _requested_rota_dates(rota_query)
                rows = self._query_staff_rota_rows(
                    rota_query,
                    scopes,
                    limit,
                    source_filenames=_rota_csv_filenames(rota_query, table_assets or csv_assets or [], selected_tables),
                )
                role_groups = _requested_rota_role_groups(rota_query)
                if not rows and role_groups == {"doctor"} and not requested_rota_dates:
                    rows.extend(
                        self._lookup_category(
                            "doctors",
                            query,
                            scopes,
                            limit - len(rows),
                            stopwords=lookup_stopwords,
                        )
                    )
                if not rows and not role_groups and not requested_rota_dates and _requires_on_call(query):
                    rows.extend(
                        self._lookup_category(
                            "doctors",
                            "doctor on call",
                            scopes,
                            limit - len(rows),
                            stopwords=lookup_stopwords,
                        )
                    )
            elif category == "directory" and _has_generic_info_intent(query):
                formulary_rows = self._lookup_category(
                    "formulary",
                    query,
                    scopes,
                    limit,
                    stopwords=lookup_stopwords,
                )
                rows = [
                    row for row in formulary_rows
                    if _row_matches_query_entity(row, query, ("medicine_name", "medicine", "drug"))
                ]
                if rows:
                    category = "formulary"
                    matched_table_sources = ["formulary"]
            elif selected_tables and category_first:
                rows = self._lookup_category(category, query, scopes, limit, stopwords=lookup_stopwords)
                if not rows and not authoritative_patient_lookup:
                    row_value_search_used = True
                    rows = self._query_table_value_rows(
                        query,
                        scopes,
                        limit,
                        table_names=selected_tables,
                        stopwords=row_value_count_stopwords,
                    )
                matched_table_sources = _source_tables(rows)
            elif selected_tables:
                row_value_search_used = True
                rows = self._query_table_value_rows(
                    query,
                    scopes,
                    limit,
                    table_names=selected_tables,
                    stopwords=row_value_count_stopwords,
                )
                if aggregate_intent == "count":
                    counts_by_source = self._count_table_value_rows(
                        query,
                        scopes,
                        table_names=selected_tables,
                        stopwords=row_value_count_stopwords,
                    )
                    aggregate_result = {
                        "type": "count",
                        "matching_rows": sum(counts_by_source.values()),
                        "counts_by_source": counts_by_source,
                        "source_tables": sorted(counts_by_source) or selected_tables,
                    }
                if len(rows) < limit and aggregate_intent != "count":
                    rows.extend(
                        self._lookup_category(
                            category,
                            query,
                            scopes,
                            limit - len(rows),
                            stopwords=lookup_stopwords,
                        )
                    )
                matched_table_sources = _source_tables(rows)
            else:
                row_first = aggregate_intent == "count" and _has_row_value_intent(query)
                rows = []
                table_rows: list[dict[str, Any]] = []
                if row_first:
                    row_value_search_used = True
                    table_rows = self._query_table_value_rows(
                        query,
                        scopes,
                        limit,
                        stopwords=row_value_count_stopwords,
                    )
                    rows = table_rows
                if not rows:
                    rows = self._lookup_category(category, query, scopes, limit, stopwords=lookup_stopwords)
                    if (
                        not authoritative_patient_lookup
                        and not authoritative_list_query
                        and not (rows and category_first)
                    ):
                        table_rows = self._query_table_value_rows(
                            query,
                            scopes,
                            max(0, limit - len(rows)),
                            stopwords=row_value_count_stopwords,
                        )
                        row_value_search_used = True
                        rows = rows + table_rows
                matched_table_sources = _source_tables(table_rows)
                if aggregate_intent == "count":
                    counts_by_source = self._count_table_value_rows(
                        query,
                        scopes,
                        table_names=None,
                        stopwords=row_value_count_stopwords,
                    )
                    aggregate_result = {
                        "type": "count",
                        "matching_rows": sum(counts_by_source.values()),
                        "counts_by_source": counts_by_source,
                        "source_tables": sorted(counts_by_source),
                    }
            if row_value_search_used:
                rows, strict_row_value_filter_applied = _filter_rows_for_specific_row_values(
                    query,
                    rows,
                    row_value_count_stopwords,
                )
                if strict_row_value_filter_applied:
                    matched_table_sources = _source_tables(rows)
                    if aggregate_intent == "count":
                        counts_by_source = _counts_by_source(rows)
                        aggregate_result = {
                            "type": "count",
                            "matching_rows": sum(counts_by_source.values()),
                            "counts_by_source": counts_by_source,
                            "source_tables": sorted(counts_by_source),
                        }
            row_search_terms = _expanded_search_terms(query, row_value_count_stopwords)
            matched_terms = _matched_terms(row_search_terms, rows)
            matched_columns = _matched_columns(row_search_terms, rows)
        except Exception as exc:
            return LookupResult(
                category,
                [],
                scopes,
                f"Postgres deterministic lookup failed: {type(exc).__name__}: {exc}",
                lookup_plan={
                    "category": category,
                    "search_terms": search_terms,
                    "selected_table_assets": selected_assets,
                    "aggregate_intent": aggregate_intent,
                    "aggregate_result": aggregate_result,
                    "row_value_search_used": row_value_search_used,
                    "strict_row_value_filter_applied": strict_row_value_filter_applied,
                    "distinct_field": distinct_field,
                    "matched_table_sources": matched_table_sources,
                    "matched_csv_sources": matched_table_sources,
                    "matched_terms": matched_terms,
                    "matched_columns": matched_columns,
                    "resolved_today": resolved_today,
                    "requested_rota_dates": requested_rota_dates,
                    "date_grounding_rule": (
                        "Do not call any rota row 'today' unless its row date equals resolved_today."
                    ),
                    "source": "postgres",
                },
            )

        if category == "staff_rota":
            message = self._staff_rota_message(query, rows)
        elif authoritative_patient_lookup and not rows:
            message = "No matching patient found."
        else:
            message = "No matching rows found." if not rows else f"Found {len(rows)} matching row(s)."
        legacy_matched_sources = _source_tables(rows) or matched_table_sources
        return LookupResult(
            category,
            rows,
            scopes,
            message,
            lookup_plan={
                "category": category,
                "search_terms": search_terms,
                "selected_table_assets": selected_assets,
                "aggregate_intent": aggregate_intent,
                "aggregate_result": aggregate_result,
                "row_value_search_used": row_value_search_used,
                "strict_row_value_filter_applied": strict_row_value_filter_applied,
                "distinct_field": distinct_field,
                "matched_table_sources": matched_table_sources,
                "matched_csv_sources": legacy_matched_sources,
                "matched_terms": matched_terms,
                "matched_columns": matched_columns,
                "resolved_today": resolved_today,
                "requested_rota_dates": requested_rota_dates,
                "date_grounding_rule": "Do not call any rota row 'today' unless its row date equals resolved_today.",
                "source": "postgres",
            },
        )

    def _staff_rota_message(self, query: str, rows: Sequence[dict[str, Any]]) -> str:
        rota_query = _staff_rota_query_focus(query)
        requested_dates = _requested_rota_dates(rota_query)
        requested_groups = _requested_rota_role_groups(rota_query)
        if not rows:
            if requested_dates:
                return (
                    "No matching on-call staff rows found for requested date(s): "
                    + ", ".join(requested_dates)
                    + ". Do not use rows from other dates as the requested rota."
                )
            return "No matching on-call staff rows found."

        uses_staff_rota_rows = any(
            isinstance(row, dict) and str(row.get("source_table") or "").lower() == "staff_schedule"
            for row in rows
        )
        found_dates: set[str] = set()
        found_groups: set[str] = set()
        for result_row in rows:
            payload = result_row.get("row") if isinstance(result_row, dict) else {}
            if not isinstance(payload, dict):
                payload = result_row if isinstance(result_row, dict) else {}
            if not isinstance(payload, dict):
                continue
            if payload.get("date"):
                found_dates.add(str(payload["date"]))
            role = str(payload.get("role") or payload.get("grade") or "").lower()
            doctor_value = str(payload.get("doctor") or payload.get("clinician") or "").strip()
            if any(marker in role for marker in ["consultant", "physician", "registrar", "doctor", "clinician"]):
                found_groups.add("doctor")
            if doctor_value:
                found_groups.add("doctor")
            if "nurse" in role:
                found_groups.add("nurse")

        notes = [
            f"Found {len(rows)} matching staff_schedule row(s)."
            if uses_staff_rota_rows
            else f"Found {len(rows)} matching on-call staff row(s)."
        ]
        if requested_dates:
            notes.append("Requested dates: " + ", ".join(requested_dates) + ".")
            missing_dates = [value for value in requested_dates if value not in found_dates]
            if missing_dates:
                notes.append("No matching rows found for: " + ", ".join(missing_dates) + ".")
        if requested_groups:
            missing_groups = sorted(requested_groups - found_groups)
            if missing_groups:
                notes.append("No matching " + ", ".join(missing_groups) + " rows found for the requested date range.")
        return " ".join(notes)

    def ingest_uploaded_csv(
        self,
        filename: str,
        data: bytes,
        access_level: str = "all_staff",
    ) -> CsvTableSyncResult:
        semantic_metadata = build_csv_semantic_metadata(filename, data)
        columns = [str(column).strip() for column in semantic_metadata.get("columns") or [] if str(column).strip()]
        mapping = detect_csv_table_mapping(filename, columns)
        if mapping is None:
            raise UnsupportedCsvLookupError(filename, columns)

        decoded = data.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames:
            raise UnsupportedCsvLookupError(filename, [])

        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {
                str(key).strip(): str(value).strip()
                for key, value in row.items()
                if key is not None and value is not None and str(value).strip()
            }
            if not cleaned:
                continue
            cleaned.setdefault("access_level", access_level)
            rows.append(cleaned)

        if not rows:
            raise UnsupportedCsvLookupError(filename, columns)

        with self._connect() as conn:
            with conn.cursor() as cur:
                self._sync_known_csv_table(cur, filename, rows, table_key=str(mapping["table_key"]))
            conn.commit()
        return CsvTableSyncResult(
            filename=filename,
            table_key=str(mapping["table_key"]),
            table_name=str(mapping["table_name"]),
            rows_inserted=len(rows),
            columns=columns,
            semantic_metadata=semantic_metadata,
        )

    def _sync_known_csv_table(self, cur, filename: str, rows: Sequence[dict[str, str]], *, table_key: str | None = None) -> None:
        normalized = filename.lower()
        resolved_table_key = table_key or str((detect_csv_table_mapping(filename, rows[0].keys() if rows else []) or {}).get("table_key") or "")
        if normalized == "staff_rota.csv" or resolved_table_key == "schedule":
            self._sync_staff_schedule_rows(cur, rows)
        elif normalized == "appointment_clinics.csv" or resolved_table_key == "clinic_sessions":
            self._sync_clinic_session_rows(cur, rows)
        elif normalized == "equipment_assets.csv" or resolved_table_key == "equipment":
            self._sync_equipment_asset_rows(cur, rows)
        elif normalized == "medication_formulary.csv" or resolved_table_key == "formulary":
            self._sync_formulary_rows(cur, rows)
        elif normalized == "ward_directory.csv" or resolved_table_key == "wards":
            self._sync_ward_rows(cur, rows)
        elif normalized == "department_contacts.csv" or resolved_table_key == "contacts":
            self._sync_contact_rows(cur, rows)
        elif normalized == "audit_schedule.csv" or resolved_table_key == "compliance_audits":
            self._sync_audit_rows(cur, rows)
        elif normalized == "training_compliance.csv" or resolved_table_key == "training":
            self._sync_training_rows(cur, rows)
        else:
            raise UnsupportedCsvLookupError(filename, rows[0].keys() if rows else [])

    def _sync_staff_schedule_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for index, row in enumerate(rows, start=1):
            department = row.get("department", "")
            shift_date = row.get("date") or row.get("shift_date")
            if str(shift_date).strip().lower() == "today":
                shift_date = date.today().isoformat()
            elif str(shift_date).strip().lower() == "tomorrow":
                shift_date = (date.today() + timedelta(days=1)).isoformat()
            cur.execute(
                """
                INSERT INTO staff_schedule
                    (schedule_id, shift_date, department_id, department_name, role, staff_name,
                     shift_start, shift_end, on_call, contact, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (schedule_id) DO UPDATE SET
                    shift_date = EXCLUDED.shift_date,
                    department_id = EXCLUDED.department_id,
                    department_name = EXCLUDED.department_name,
                    role = EXCLUDED.role,
                    staff_name = EXCLUDED.staff_name,
                    shift_start = EXCLUDED.shift_start,
                    shift_end = EXCLUDED.shift_end,
                    on_call = EXCLUDED.on_call,
                    contact = EXCLUDED.contact,
                    access_level = EXCLUDED.access_level
                """,
                (
                    row.get("schedule_id") or f"SCH-CSV-{index:04d}",
                    shift_date,
                    _department_id_for_name(department),
                    department,
                    row.get("role") or ("Doctor" if row.get("doctor") else ""),
                    row.get("staff_name") or row.get("name") or row.get("doctor") or row.get("clinician") or "",
                    row.get("shift_start") or "00:00",
                    row.get("shift_end") or "00:00",
                    _truthy(row.get("on_call") or row.get("status") or "yes"),
                    row.get("contact") or "",
                    row.get("access_level") or "clinical",
                ),
            )

    def _sync_clinic_session_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for row in rows:
            cur.execute(
                """
                INSERT INTO clinic_sessions
                    (clinic_id, clinic_name, clinic_date, start_time, consultant, slots_total,
                     slots_available, referral_priority, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (clinic_id) DO UPDATE SET
                    clinic_name = EXCLUDED.clinic_name,
                    clinic_date = EXCLUDED.clinic_date,
                    start_time = EXCLUDED.start_time,
                    consultant = EXCLUDED.consultant,
                    slots_total = EXCLUDED.slots_total,
                    slots_available = EXCLUDED.slots_available,
                    referral_priority = EXCLUDED.referral_priority,
                    access_level = EXCLUDED.access_level
                """,
                (
                    row.get("clinic_id"),
                    row.get("clinic_name", ""),
                    row.get("date"),
                    row.get("start_time") or "00:00",
                    row.get("consultant", ""),
                    int(row.get("slots_total") or 0),
                    int(row.get("slots_available") or 0),
                    row.get("referral_priority", ""),
                    row.get("access_level") or "clinical",
                ),
            )

    def _sync_equipment_asset_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for row in rows:
            cur.execute(
                """
                INSERT INTO equipment_assets
                    (asset_id, equipment_type, location, status, last_service_date,
                     next_service_due, clinical_engineering_contact, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (asset_id) DO UPDATE SET
                    equipment_type = EXCLUDED.equipment_type,
                    location = EXCLUDED.location,
                    status = EXCLUDED.status,
                    last_service_date = EXCLUDED.last_service_date,
                    next_service_due = EXCLUDED.next_service_due,
                    clinical_engineering_contact = EXCLUDED.clinical_engineering_contact,
                    access_level = EXCLUDED.access_level
                """,
                (
                    row.get("asset_id"),
                    row.get("equipment_type", ""),
                    row.get("location", ""),
                    row.get("status", ""),
                    row.get("last_service_date") or None,
                    row.get("next_service_due") or None,
                    row.get("clinical_engineering_contact", ""),
                    row.get("access_level") or "all_staff",
                ),
            )

    def _sync_formulary_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for row in rows:
            medicine_name = row.get("medicine") or row.get("medicine_name") or row.get("drug") or ""
            if not medicine_name:
                continue
            cur.execute("SELECT medicine_id FROM formulary WHERE lower(medicine_name) = lower(%s) LIMIT 1", (medicine_name,))
            existing = cur.fetchone()
            medicine_id = (existing or {}).get("medicine_id") if existing else _generated_id("MED", medicine_name)
            cur.execute(
                """
                INSERT INTO formulary
                    (medicine_id, medicine_name, category, restricted, approval_required,
                     max_adult_dose, monitoring_required, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (medicine_id) DO UPDATE SET
                    medicine_name = EXCLUDED.medicine_name,
                    category = EXCLUDED.category,
                    restricted = EXCLUDED.restricted,
                    approval_required = EXCLUDED.approval_required,
                    max_adult_dose = EXCLUDED.max_adult_dose,
                    monitoring_required = EXCLUDED.monitoring_required,
                    access_level = EXCLUDED.access_level
                """,
                (
                    medicine_id,
                    medicine_name,
                    row.get("category", ""),
                    _truthy(row.get("restricted")),
                    row.get("approval_required", ""),
                    row.get("max_adult_dose", ""),
                    row.get("monitoring_required", ""),
                    row.get("access_level") or "all_staff",
                ),
            )

    def _sync_ward_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for row in rows:
            department = row.get("specialty") or row.get("department") or ""
            cur.execute(
                """
                INSERT INTO wards
                    (ward_code, ward_name, department_id, department_name, floor, bed_capacity,
                     beds_available, nurse_in_charge, phone, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, COALESCE((SELECT beds_available FROM wards WHERE ward_code = %s), 0), %s, %s, %s)
                ON CONFLICT (ward_code) DO UPDATE SET
                    ward_name = EXCLUDED.ward_name,
                    department_id = EXCLUDED.department_id,
                    department_name = EXCLUDED.department_name,
                    floor = EXCLUDED.floor,
                    bed_capacity = EXCLUDED.bed_capacity,
                    nurse_in_charge = EXCLUDED.nurse_in_charge,
                    phone = EXCLUDED.phone,
                    access_level = EXCLUDED.access_level
                """,
                (
                    row.get("ward_code"),
                    row.get("ward_name", ""),
                    _department_id_for_name(department),
                    department,
                    row.get("floor") or "",
                    int(row.get("bed_capacity") or 0),
                    row.get("ward_code"),
                    row.get("nurse_in_charge") or "",
                    row.get("phone") or "",
                    row.get("access_level") or "all_staff",
                ),
            )

    def _sync_contact_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for index, row in enumerate(rows, start=1):
            department = row.get("department") or ""
            cur.execute(
                """
                INSERT INTO organization_contacts
                    (contact_id, contact_type, department_id, department_name, contact_name, role,
                     phone, email, available_hours, escalation_level, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (contact_id) DO UPDATE SET
                    contact_type = EXCLUDED.contact_type,
                    department_id = EXCLUDED.department_id,
                    department_name = EXCLUDED.department_name,
                    contact_name = EXCLUDED.contact_name,
                    role = EXCLUDED.role,
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email,
                    available_hours = EXCLUDED.available_hours,
                    escalation_level = EXCLUDED.escalation_level,
                    access_level = EXCLUDED.access_level
                """,
                (
                    row.get("contact_id") or f"CON-CSV-{index:04d}",
                    row.get("escalation_type") or row.get("contact_type") or "",
                    _department_id_for_name(department),
                    department,
                    row.get("contact_name") or "",
                    row.get("role") or "",
                    row.get("phone") or "",
                    row.get("email") or "",
                    row.get("available_hours") or "",
                    "urgent" if "urgent" in (row.get("escalation_type") or "").lower() else "routine",
                    row.get("access_level") or "all_staff",
                ),
            )

    def _sync_audit_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for row in rows:
            department = row.get("department") or ""
            cur.execute(
                """
                INSERT INTO compliance_audits
                    (audit_id, topic, department_id, department_name, lead, due_date, status,
                     last_score_percent, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_id) DO UPDATE SET
                    topic = EXCLUDED.topic,
                    department_id = EXCLUDED.department_id,
                    department_name = EXCLUDED.department_name,
                    lead = EXCLUDED.lead,
                    due_date = EXCLUDED.due_date,
                    status = EXCLUDED.status,
                    last_score_percent = EXCLUDED.last_score_percent,
                    access_level = EXCLUDED.access_level
                """,
                (
                    row.get("audit_id"),
                    row.get("topic") or "",
                    _department_id_for_name(department),
                    department,
                    row.get("lead") or "",
                    row.get("due_date"),
                    row.get("status") or "",
                    int(row.get("last_score_percent") or 0),
                    row.get("access_level") or "manager",
                ),
            )

    def _sync_training_rows(self, cur, rows: Sequence[dict[str, str]]) -> None:
        for row in rows:
            department = row.get("department") or ""
            training_id = row.get("training_id") or _generated_id("TRN", row.get("staff_id", ""), row.get("training_module", ""))
            cur.execute(
                """
                INSERT INTO training_records
                    (training_id, staff_name, role, department_id, department_name, training_module,
                     completion_date, expiry_date, status, access_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (training_id) DO UPDATE SET
                    staff_name = EXCLUDED.staff_name,
                    role = EXCLUDED.role,
                    department_id = EXCLUDED.department_id,
                    department_name = EXCLUDED.department_name,
                    training_module = EXCLUDED.training_module,
                    completion_date = EXCLUDED.completion_date,
                    expiry_date = EXCLUDED.expiry_date,
                    status = EXCLUDED.status,
                    access_level = EXCLUDED.access_level
                """,
                (
                    training_id,
                    row.get("staff_name") or "",
                    row.get("role") or "",
                    _department_id_for_name(department),
                    department,
                    row.get("training_module") or "",
                    row.get("completion_date") or None,
                    row.get("expiry_date") or None,
                    row.get("status") or "",
                    row.get("access_level") or "manager",
                ),
            )

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover - exercised when dependency missing
            raise RuntimeError("psycopg is not installed. Install backend requirements.") from exc

        return psycopg.connect(
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            dbname=self.settings.postgres_db,
            user=self.settings.postgres_user,
            password=self.settings.postgres_password,
            sslmode=self.settings.postgres_sslmode,
            row_factory=dict_row,
            connect_timeout=3,
        )

    def _lookup_category(
        self,
        category: str,
        query: str,
        scopes: tuple[str, ...],
        limit: int,
        *,
        stopwords: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        terms = _terms(query)
        primary = _best_search_term(terms, stopwords)
        with self._connect() as conn:
            with conn.cursor() as cur:
                if category == "patients":
                    return self._query_patients(cur, terms, scopes, limit, stopwords)
                if category == "doctors":
                    return self._query_doctors(cur, query, terms, scopes, limit, stopwords)
                if category == "departments":
                    return self._query_departments(cur, terms, scopes, limit, stopwords)
                if category == "contacts":
                    return self._query_contact_information(cur, terms, scopes, limit, stopwords)
                if category == "appointments":
                    return self._query_appointments(cur, terms, scopes, limit, stopwords)
                if category == "wards":
                    return self._query_wards(cur, terms, scopes, limit, stopwords)
                if category == "formulary":
                    return self._query_formulary(cur, terms, scopes, limit, stopwords)
                if category == "equipment":
                    return self._query_equipment(cur, terms, scopes, limit, stopwords)
                if category in {"clinic_sessions", "finance", "compliance_audits", "training"}:
                    return self._query_configured_table(cur, category, query, terms, scopes, limit, stopwords)
                return self._query_directory(cur, primary, scopes, limit, stopwords)

    def _query_configured_table(
        self,
        cur,
        category: str,
        query: str,
        terms: list[str],
        scopes: tuple[str, ...],
        limit: int,
        stopwords: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        config = CRM_TABLES.get(category)
        if not config:
            return []
        active_stopwords = STOPWORDS | QUERY_INTENT_MARKERS | AGGREGATE_QUERY_MARKERS | (stopwords or set())
        useful_terms = [
            term
            for term in _expanded_search_terms(query, active_stopwords)
            if len(term) > 2 and term not in active_stopwords
        ]
        where_parts = [self._access_sql()]
        params: list[Any] = [list(scopes)]
        search_columns = [column for column in config["search"] if column in config["columns"]]
        if useful_terms:
            match_parts: list[str] = []
            for term in useful_terms[:8]:
                pattern = _like(term)
                term_parts = [f"lower(CAST({column} AS TEXT)) LIKE %s" for column in search_columns]
                if term_parts:
                    match_parts.append("(" + " OR ".join(term_parts) + ")")
                    params.extend([pattern] * len(search_columns))
            if match_parts:
                where_parts.append("(" + " OR ".join(match_parts) + ")")
        elif not _has_list_intent(query):
            return []
        params.append(limit)
        cur.execute(
            f"""
            SELECT {", ".join(config["columns"])}
            FROM {config["table"]}
            WHERE {" AND ".join(where_parts)}
            ORDER BY {config["pk"]}
            LIMIT %s
            """,
            tuple(params),
        )
        return [
            self._row_from_table_result(str(config["table"]), config, dict(row))
            for row in cur.fetchall()
        ]

    def _table_configs_for_names(self, table_names: Sequence[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
        if not table_names:
            return list(CRM_TABLES.items())
        requested: set[str] = set()
        for name in table_names:
            if not str(name).strip():
                continue
            normalized_name = str(name).strip().lower()
            requested.add(_normalized_key(normalized_name))
            mapping = CSV_TABLE_MAPPINGS.get(normalized_name)
            if mapping:
                table_key = str(mapping.get("table_key") or "")
                requested.add(_normalized_key(table_key))
                if table_key in CRM_TABLES:
                    requested.add(_normalized_key(str(CRM_TABLES[table_key]["table"])))
        selected: list[tuple[str, dict[str, Any]]] = []
        for key, config in CRM_TABLES.items():
            names = {_normalized_key(key), _normalized_key(str(config["table"]))}
            if names & requested:
                selected.append((key, config))
        return selected

    def _row_from_table_result(self, table_name: str, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_table": table_name,
            "source_filename": table_name,
            "row_number": payload.get(config["pk"]),
            "row": {column: payload.get(column) for column in config["columns"]},
            "access_level": payload.get("access_level"),
        }

    def _query_table_value_rows(
        self,
        query: str,
        scopes: tuple[str, ...],
        limit: int,
        *,
        table_names: Sequence[str] | None = None,
        stopwords: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        legacy_lookup = getattr(self, "_query_uploaded_lookup_rows", None)
        if callable(legacy_lookup):
            return legacy_lookup(
                query,
                scopes,
                limit,
                source_filenames=table_names,
                stopwords=stopwords,
            )
        if limit <= 0:
            return []
        terms = _expanded_search_terms(query, stopwords or set())
        terms = [term for term in terms if len(term) > 2]
        if not terms:
            return []
        configs = self._table_configs_for_names(table_names)
        rows: list[dict[str, Any]] = []
        fetch_limit = max(limit, min(limit * 5, 250))
        with self._connect() as conn:
            with conn.cursor() as cur:
                for _, config in configs:
                    search_columns = [column for column in config["search"] if column in config["columns"]]
                    if not search_columns:
                        continue
                    score_params: list[Any] = []
                    where_params: list[Any] = []
                    match_parts: list[str] = []
                    score_parts: list[str] = []
                    for term in terms[:10]:
                        pattern = _like(term)
                        term_parts = [f"lower(CAST({column} AS TEXT)) LIKE %s" for column in search_columns]
                        match_parts.append("(" + " OR ".join(term_parts) + ")")
                        where_params.extend([pattern] * len(search_columns))
                        score_parts.extend([f"CASE WHEN lower(CAST({column} AS TEXT)) LIKE %s THEN 1 ELSE 0 END" for column in search_columns])
                        score_params.extend([pattern] * len(search_columns))
                    params = [*score_params, list(scopes), *where_params, fetch_limit]
                    cur.execute(
                        f"""
                        SELECT {", ".join(config["columns"])},
                               ({' + '.join(score_parts)}) AS match_score
                        FROM {config["table"]}
                        WHERE {self._access_sql()}
                          AND ({" OR ".join(match_parts)})
                        ORDER BY match_score DESC, {config["pk"]}
                        LIMIT %s
                        """,
                        tuple(params),
                    )
                    for result in cur.fetchall():
                        payload = dict(result)
                        payload.pop("match_score", None)
                        row = self._row_from_table_result(str(config["table"]), config, payload)
                        row["_match_score"] = int(result.get("match_score") or 0)
                        rows.append(row)
                    if len(rows) >= fetch_limit:
                        break
        rows.sort(
            key=lambda row: (
                -int(row.get("_match_score") or 0),
                str(row.get("source_table") or ""),
                str(row.get("row_number") or ""),
            )
        )
        for row in rows:
            row.pop("_match_score", None)
        return rows[:limit]

    def _count_table_value_rows(
        self,
        query: str,
        scopes: tuple[str, ...],
        *,
        table_names: Sequence[str] | None = None,
        stopwords: set[str] | None = None,
    ) -> dict[str, int]:
        legacy_count = getattr(self, "_count_uploaded_lookup_rows", None)
        if callable(legacy_count):
            return legacy_count(
                query,
                scopes,
                source_filenames=table_names,
                stopwords=stopwords,
            )
        terms = _expanded_search_terms(query, stopwords or set())
        terms = [term for term in terms if len(term) > 2]
        if not terms:
            return {}
        counts: dict[str, int] = {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                for _, config in self._table_configs_for_names(table_names):
                    search_columns = [column for column in config["search"] if column in config["columns"]]
                    if not search_columns:
                        continue
                    params: list[Any] = [list(scopes)]
                    match_parts: list[str] = []
                    for term in terms[:10]:
                        pattern = _like(term)
                        term_parts = [f"lower(CAST({column} AS TEXT)) LIKE %s" for column in search_columns]
                        match_parts.append("(" + " OR ".join(term_parts) + ")")
                        params.extend([pattern] * len(search_columns))
                    cur.execute(
                        f"""
                        SELECT count(*) AS matching_rows
                        FROM {config["table"]}
                        WHERE {self._access_sql()}
                          AND ({" OR ".join(match_parts)})
                        """,
                        tuple(params),
                    )
                    row = cur.fetchone() or {}
                    count = int(row.get("matching_rows") or 0)
                    if count:
                        counts[str(config["table"])] = count
        return counts

    def _search_terms(self, query: str, stopwords: set[str]) -> list[str]:
        active_stopwords = STOPWORDS | AGGREGATE_QUERY_MARKERS | stopwords
        return [term for term in _terms(query) if term.lower() not in active_stopwords]

    def _matching_table_assets(
        self,
        query: str,
        table_assets: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        query_terms = set()
        for term in _terms(query):
            query_terms.update(_term_variants(term))
        query_terms = {term for term in query_terms if term not in STOPWORDS and term not in AGGREGATE_QUERY_MARKERS}
        if not query_terms:
            return []
        matches: list[tuple[int, dict[str, Any]]] = []
        for asset in table_assets:
            filename = str(asset.get("filename") or "")
            table_name = str(asset.get("table_name") or asset.get("source_table") or filename or "")
            configs = self._table_configs_for_names([table_name]) if table_name else []
            if table_name and not configs:
                continue
            resolved_table = str(configs[0][1]["table"]) if configs else table_name
            title = str(asset.get("title") or asset.get("name") or table_name)
            columns = [str(column) for column in asset.get("columns") or []]
            semantic_terms = [str(term) for term in asset.get("semantic_terms") or []]
            sample_values = [str(value) for value in asset.get("sample_values") or []]
            raw_categorical = asset.get("categorical_values") or {}
            categorical_values: list[str] = []
            if isinstance(raw_categorical, dict):
                for values in raw_categorical.values():
                    categorical_values.extend(str(value) for value in values or [])
            elif isinstance(raw_categorical, list):
                categorical_values.extend(str(value) for value in raw_categorical)

            filename_terms = _normalized_terms(" ".join([table_name, title]))
            column_terms = set().union(*(_normalized_terms(column) for column in columns)) if columns else set()
            semantic_field_terms = set().union(*(_normalized_terms(term) for term in semantic_terms)) if semantic_terms else set()
            categorical_terms = (
                set().union(*(_normalized_terms(value) for value in categorical_values)) if categorical_values else set()
            )
            sample_terms = set().union(*(_normalized_terms(value) for value in sample_values)) if sample_values else set()

            score = 0
            score += 5 * sum(1 for term in query_terms if term in column_terms)
            score += 4 * sum(1 for term in query_terms if term in filename_terms)
            score += 4 * sum(1 for term in query_terms if term in categorical_terms)
            score += 3 * sum(1 for term in query_terms if term in semantic_field_terms)
            score += 1 * sum(1 for term in query_terms if term in sample_terms)
            if score:
                matches.append(
                    (
                        score,
                        {
                            "table_name": resolved_table,
                            "table_key": str(asset.get("table_key") or asset.get("section") or ""),
                            "filename": filename or resolved_table,
                            "title": title,
                            "columns": columns[:20],
                            "row_count": int(asset.get("row_count") or 0),
                            "semantic_terms": semantic_terms[:30],
                            "categorical_values": raw_categorical,
                            "sample_values": sample_values[:20],
                            "match_score": score,
                        },
                    )
                )
        matches.sort(key=lambda item: (-item[0], item[1]["table_name"]))
        return [asset for _, asset in matches[:5]]

    def _matching_csv_assets(
        self,
        query: str,
        csv_assets: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._matching_table_assets(query, csv_assets)

    def _classify(self, query: str) -> str:
        q = query.lower()
        terms = _terms(query)
        appointment_query = any(marker in q for marker in ["appointment", "appointments", "clinic", "slot", "referral"])
        if appointment_query:
            return "appointments"
        if _is_staff_rota_query(query):
            return "staff_rota"
        if any(marker in q for marker in ["audit", "audits", "compliance audit", "compliance audits"]):
            return "compliance_audits"
        if any(marker in q for marker in ["training", "competency", "competencies", "mandatory training"]):
            return "training"
        if any(marker in q for marker in ["finance", "financial", "invoice", "invoices", "balance", "payer", "billing"]):
            return "finance"
        if any(marker in q for marker in ["contact", "phone", "email", "bleep", "extension", "call", "reach"]):
            return "contacts"
        patient_location_query = any(
            marker in q for marker in ["ward", "bed", "ipd", "inpatient", "location", "located", "where"]
        )
        if patient_location_query and _has_person_name_hint(terms):
            return "patients"
        if any(marker in q for marker in ["patient", "mrn", "nhs", "date of birth", "dob"]):
            return "patients"
        if any(marker in q for marker in ["doctor", "physician", "consultant", "clinician"]):
            return "doctors"
        if any(marker in q for marker in ["department", "service", "unit"]):
            return "departments"
        if any(marker in q for marker in ["ward", "bed", "floor"]):
            return "wards"
        if any(marker in q for marker in ["medicine", "drug", "formulary", "restricted", "dose"]):
            return "formulary"
        if any(marker in q for marker in ["equipment", "asset", "device", "ventilator", "defibrillator", "pump", "monitor", "machine"]):
            return "equipment"
        return "directory"

    def _access_sql(self) -> str:
        return self._qualified_access_sql()

    def _qualified_access_sql(self, table_alias: str = "") -> str:
        qualifier = f"{table_alias}." if table_alias else ""
        return f"({qualifier}access_level = ANY(%s) OR {qualifier}access_level IS NULL)"

    def _query_staff_rota_rows(
        self,
        query: str,
        scopes: tuple[str, ...],
        limit: int,
        *,
        source_filenames: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        lookup_scopes = _staff_rota_access_scopes(scopes)
        rota_query = _staff_rota_query_focus(query)
        requested_dates = _requested_rota_dates(rota_query)
        requested_groups = _requested_rota_role_groups(rota_query)
        department_terms = [
            term
            for term in _expanded_search_terms(
                rota_query,
                STOPWORDS | STAFF_ROTA_QUERY_MARKERS | DOCTOR_ROLE_MARKERS | NURSE_ROLE_MARKERS,
            )
            if term not in {"list", "me", "available", "availability", "today", "tomorrow", "csv", "file"}
        ]
        return self._query_staff_schedule_table(
            query,
            lookup_scopes,
            limit,
            requested_dates=requested_dates,
            requested_groups=requested_groups,
            department_terms=department_terms,
        )

    def _query_staff_schedule_table(
        self,
        query: str,
        scopes: tuple[str, ...],
        limit: int,
        *,
        requested_dates: Sequence[str] | None = None,
        requested_groups: set[str] | None = None,
        department_terms: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        where_parts = [self._access_sql()]
        params: list[Any] = [list(scopes)]
        if requested_dates:
            where_parts.append("shift_date::text = ANY(%s)")
            params.append(list(requested_dates))
        if _requires_on_call(query):
            where_parts.append("on_call = true")

        role_filters: list[str] = []
        groups = requested_groups or set()
        if "doctor" in groups:
            role_filters.extend(["%consultant%", "%physician%", "%registrar%", "%doctor%", "%clinician%"])
        if "nurse" in groups:
            role_filters.append("%nurse%")
        if role_filters:
            where_parts.append("(" + " OR ".join(["lower(role) LIKE %s OR lower(staff_name) LIKE %s" for _ in role_filters]) + ")")
            for pattern in role_filters:
                params.extend([pattern, pattern])

        department_patterns = [_like(term) for term in list(department_terms or [])[:8]]
        if department_patterns:
            where_parts.append(
                "("
                + " OR ".join(
                    ["lower(department_name) LIKE %s OR lower(staff_name) LIKE %s OR lower(role) LIKE %s" for _ in department_patterns]
                )
                + ")"
            )
            for pattern in department_patterns:
                params.extend([pattern, pattern, pattern])

        params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT schedule_id, shift_date AS date, department_name AS department,
                           role, staff_name, shift_start, shift_end, on_call, contact, access_level
                    FROM staff_schedule
                    WHERE {" AND ".join(where_parts)}
                    ORDER BY shift_date, department_name, role, staff_name
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = []
                for row in cur.fetchall():
                    row_dict = dict(row)
                    rows.append(
                        {
                            "source_table": "staff_schedule",
                            "source_filename": "staff_schedule",
                            "row_number": row_dict.get("schedule_id"),
                            "row": {
                                "date": str(row_dict.get("date") or ""),
                                "department": row_dict.get("department"),
                                "role": row_dict.get("role"),
                                "staff_name": row_dict.get("staff_name"),
                                "shift_start": str(row_dict.get("shift_start") or ""),
                                "shift_end": str(row_dict.get("shift_end") or ""),
                                "on_call": "Yes" if row_dict.get("on_call") else "No",
                                "contact": row_dict.get("contact"),
                            },
                            "access_level": row_dict.get("access_level"),
                        }
                    )
                return rows

    def _query_staff_rota_local_csv(
        self,
        query: str,
        scopes: tuple[str, ...],
        limit: int,
        *,
        requested_dates: Sequence[str] | None = None,
        requested_groups: set[str] | None = None,
        department_terms: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.settings:
            return []
        rota_path = Path(self.settings.local_data_dir) / "raw" / "staff_rota.csv"
        if not rota_path.exists():
            return []

        lookup_scopes = _staff_rota_access_scopes(scopes)
        dates = set(requested_dates or _requested_rota_dates(query))
        role_groups = requested_groups if requested_groups is not None else _requested_rota_role_groups(query)
        search_terms = [term.lower() for term in (department_terms or [])]
        require_on_call = _requires_on_call(query)

        rows: list[dict[str, Any]] = []
        with rota_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, payload in enumerate(reader, start=1):
                cleaned = {str(key).strip(): str(value).strip() for key, value in payload.items() if key}
                access_level = cleaned.get("access_level") or "all_staff"
                if access_level not in lookup_scopes:
                    continue
                if dates and cleaned.get("date") not in dates:
                    continue
                if require_on_call and cleaned.get("on_call", "yes").strip().lower() not in {"yes", "true", "1", "y"}:
                    continue
                role = cleaned.get("role", "").lower()
                if role_groups and not (
                    ("doctor" in role_groups and any(marker in role for marker in ["consultant", "physician", "registrar", "doctor", "clinician"]))
                    or ("nurse" in role_groups and "nurse" in role)
                ):
                    continue
                if search_terms:
                    haystack = " ".join(
                        [
                            cleaned.get("department", ""),
                            cleaned.get("staff_name", ""),
                            cleaned.get("role", ""),
                            cleaned.get("contact", ""),
                        ]
                    ).lower()
                    if not any(term in haystack for term in search_terms):
                        continue
                rows.append(
                    {
                        "source_table": "local_csv",
                        "source_filename": "staff_rota.csv",
                        "row_number": row_number,
                        "row": cleaned,
                        "access_level": access_level,
                    }
                )
                if len(rows) >= limit:
                    break
        return rows

    def crm_sections(self) -> dict[str, Any]:
        return {
            section: {
                "primary_key": config["pk"],
                "columns": list(config["columns"]),
                "filters": list(config.get("filters") or []),
            }
            for section, config in CRM_TABLES.items()
        }

    def crm_list(
        self,
        section: str,
        user: HealthcareUserContext,
        *,
        query: str = "",
        filters: dict[str, str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        config = self._crm_config(section)
        scopes = _access_scopes(user)
        filters = {str(key): str(value).strip() for key, value in (filters or {}).items() if str(value).strip()}
        where_parts = [self._access_sql()]
        params: list[Any] = [list(scopes)]
        search = query.strip()
        if search:
            pattern = _like(search)
            search_columns = [column for column in config["search"] if column in config["columns"]]
            where_parts.append("(" + " OR ".join([f"lower(CAST({column} AS TEXT)) LIKE %s" for column in search_columns]) + ")")
            params.extend([pattern] * len(search_columns))
        for column in config.get("filters") or []:
            value = filters.get(column)
            if not value:
                continue
            if column.startswith("on_call"):
                where_parts.append(f"{column} = %s")
                params.append(_truthy(value))
            else:
                where_parts.append(f"lower(CAST({column} AS TEXT)) LIKE %s")
                params.append(_like(value))
        limit = max(1, min(limit, 500))
        params.append(limit)
        columns = ", ".join(config["columns"])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {columns}
                    FROM {config["table"]}
                    WHERE {" AND ".join(where_parts)}
                    ORDER BY {config["pk"]}
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = [dict(row) for row in cur.fetchall()]
        return {
            "section": section,
            "primary_key": config["pk"],
            "columns": list(config["columns"]),
            "filters": list(config.get("filters") or []),
            "rows": rows,
            "summary": {
                "row_count": len(rows),
                "message": "No matching rows found." if not rows else f"Found {len(rows)} matching row(s).",
            },
        }

    def crm_create(self, section: str, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._crm_config(section)
        values = self._crm_payload(config, payload, require_pk=True)
        columns = list(values)
        placeholders = ", ".join(["%s"] * len(columns))
        assignments = ", ".join([f"{column} = EXCLUDED.{column}" for column in columns if column != config["pk"]])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {config["table"]} ({", ".join(columns)})
                    VALUES ({placeholders})
                    ON CONFLICT ({config["pk"]}) DO UPDATE SET {assignments}
                    RETURNING {", ".join(config["columns"])}
                    """,
                    tuple(values[column] for column in columns),
                )
                row = dict(cur.fetchone() or {})
            conn.commit()
        return row

    def crm_update(self, section: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._crm_config(section)
        values = self._crm_payload(config, payload, require_pk=False)
        if not values:
            return self.crm_get(section, record_id)
        assignments = ", ".join([f"{column} = %s" for column in values])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {config["table"]}
                    SET {assignments}
                    WHERE {config["pk"]} = %s
                    RETURNING {", ".join(config["columns"])}
                    """,
                    tuple(values.values()) + (record_id,),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise ValueError(f"{section} record not found: {record_id}")
        return dict(row)

    def crm_delete(self, section: str, record_id: str) -> dict[str, Any]:
        config = self._crm_config(section)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {config['table']} WHERE {config['pk']} = %s RETURNING {config['pk']}",
                    (record_id,),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise ValueError(f"{section} record not found: {record_id}")
        return {"deleted": True, "section": section, "record_id": record_id}

    def crm_get(self, section: str, record_id: str) -> dict[str, Any]:
        config = self._crm_config(section)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {', '.join(config['columns'])} FROM {config['table']} WHERE {config['pk']} = %s",
                    (record_id,),
                )
                row = cur.fetchone()
        if not row:
            raise ValueError(f"{section} record not found: {record_id}")
        return dict(row)

    def _crm_config(self, section: str) -> dict[str, Any]:
        normalized = section.strip().lower().replace("-", "_")
        if normalized not in CRM_TABLES:
            raise ValueError(f"Unknown CRM section: {section}")
        return CRM_TABLES[normalized]

    def _crm_payload(self, config: dict[str, Any], payload: dict[str, Any], *, require_pk: bool) -> dict[str, Any]:
        allowed = set(config["columns"])
        values = {
            str(key): value
            for key, value in (payload or {}).items()
            if str(key) in allowed and value not in (None, "")
        }
        if not require_pk:
            values.pop(config["pk"], None)
        if require_pk and not values.get(config["pk"]):
            raise ValueError(f"Missing primary key: {config['pk']}")
        return values

    def patient_dashboard(
        self,
        user: HealthcareUserContext,
        query: str = "",
        patient_identifier: str = "",
        department: str = "",
        ward: str = "",
        care_status: str = "",
        tables: Sequence[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return role-scoped patient detail rows for the admin dashboard."""
        if not self.settings.deterministic_lookup_enabled:
            return {
                "available_tables": ["patients", "appointments"],
                "access_scopes_applied": list(_access_scopes(user)),
                "rows": [],
                "summary": {
                    "row_count": 0,
                    "unique_patients": 0,
                    "table_counts": {},
                    "message": "Deterministic lookup is disabled.",
                },
            }

        selected_tables = [table for table in (tables or ["patients", "appointments"]) if table in {"patients", "appointments"}]
        if not selected_tables:
            selected_tables = ["patients", "appointments"]

        scopes = _access_scopes(user)
        rows: list[dict[str, Any]] = []
        with self._connect() as conn:
            with conn.cursor() as cur:
                if "patients" in selected_tables:
                    rows.extend(
                        self._dashboard_patient_rows(
                            cur,
                            scopes=scopes,
                            query=query,
                            patient_identifier=patient_identifier,
                            department=department,
                            ward=ward,
                            care_status=care_status,
                            limit=limit,
                        )
                    )
                if "appointments" in selected_tables:
                    rows.extend(
                        self._dashboard_appointment_rows(
                            cur,
                            scopes=scopes,
                            query=query,
                            patient_identifier=patient_identifier,
                            department=department,
                            ward=ward,
                            care_status=care_status,
                            limit=limit,
                        )
                    )

        rows = rows[:limit]
        table_counts: dict[str, int] = {}
        patient_ids: set[str] = set()
        for row in rows:
            table = str(row.get("table") or "unknown")
            table_counts[table] = table_counts.get(table, 0) + 1
            patient_id = str(row.get("patient_id") or row.get("mrn") or "")
            if patient_id:
                patient_ids.add(patient_id)

        return {
            "available_tables": ["patients", "appointments"],
            "access_scopes_applied": list(scopes),
            "filters": {
                "query": query,
                "patient_identifier": patient_identifier,
                "department": department,
                "ward": ward,
                "care_status": care_status,
                "tables": selected_tables,
                "limit": limit,
            },
            "summary": {
                "row_count": len(rows),
                "unique_patients": len(patient_ids),
                "table_counts": table_counts,
                "message": "No matching rows found." if not rows else f"Found {len(rows)} matching row(s).",
            },
            "rows": rows,
        }

    def _dashboard_patient_rows(
        self,
        cur,
        scopes: tuple[str, ...],
        query: str,
        patient_identifier: str,
        department: str,
        ward: str,
        care_status: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        search = _like(query.strip()) if query.strip() else "%"
        identifier = _like(patient_identifier.strip()) if patient_identifier.strip() else "%"
        department_filter = _like(department.strip()) if department.strip() else "%"
        ward_filter = _like(ward.strip()) if ward.strip() else "%"
        status_filter = _like(care_status.strip()) if care_status.strip() else "%"
        cur.execute(
            f"""
            SELECT 'patients' AS source_table, patient_id, mrn, nhs_number, full_name AS patient_name,
                   date_of_birth, ward_code, department_name, named_consultant, care_status,
                   risk_flags, access_level
            FROM patients
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(patient_id) LIKE %s OR lower(mrn) LIKE %s OR lower(nhs_number) LIKE %s)
              AND (%s = '%%' OR lower(department_name) LIKE %s)
              AND (%s = '%%' OR lower(ward_code) LIKE %s)
              AND (%s = '%%' OR lower(care_status) LIKE %s)
              AND (%s = '%%' OR lower(full_name) LIKE %s OR lower(mrn) LIKE %s OR lower(nhs_number) LIKE %s
                   OR lower(department_name) LIKE %s OR lower(ward_code) LIKE %s
                   OR lower(named_consultant) LIKE %s OR lower(care_status) LIKE %s OR lower(risk_flags) LIKE %s)
            ORDER BY full_name
            LIMIT %s
            """,
            (
                list(scopes),
                identifier,
                identifier,
                identifier,
                identifier,
                department_filter,
                department_filter,
                ward_filter,
                ward_filter,
                status_filter,
                status_filter,
                search,
                search,
                search,
                search,
                search,
                search,
                search,
                search,
                search,
                limit,
            ),
        )
        rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["table"] = row.pop("source_table", "patients")
        return rows

    def _dashboard_appointment_rows(
        self,
        cur,
        scopes: tuple[str, ...],
        query: str,
        patient_identifier: str,
        department: str,
        ward: str,
        care_status: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        search = _like(query.strip()) if query.strip() else "%"
        identifier = _like(patient_identifier.strip()) if patient_identifier.strip() else "%"
        department_filter = _like(department.strip()) if department.strip() else "%"
        ward_filter = _like(ward.strip()) if ward.strip() else "%"
        status_filter = _like(care_status.strip()) if care_status.strip() else "%"
        cur.execute(
            f"""
            SELECT 'appointments' AS source_table, p.patient_id, a.patient_mrn AS mrn, p.nhs_number,
                   a.patient_name, p.date_of_birth, p.ward_code, a.department_name,
                   p.named_consultant, p.care_status, p.risk_flags,
                   a.appointment_id, a.clinic_name, a.appointment_date, a.appointment_time,
                   a.clinician_name, a.status, a.referral_priority, a.access_level
            FROM appointments a
            LEFT JOIN patients p ON p.mrn = a.patient_mrn
            WHERE {self._qualified_access_sql("a")}
              AND (%s = '%%' OR lower(COALESCE(p.patient_id, '')) LIKE %s OR lower(a.patient_mrn) LIKE %s
                   OR lower(COALESCE(p.nhs_number, '')) LIKE %s)
              AND (%s = '%%' OR lower(a.department_name) LIKE %s)
              AND (%s = '%%' OR lower(COALESCE(p.ward_code, '')) LIKE %s)
              AND (%s = '%%' OR lower(COALESCE(p.care_status, '')) LIKE %s)
              AND (%s = '%%' OR lower(a.patient_name) LIKE %s OR lower(a.patient_mrn) LIKE %s
                   OR lower(a.clinic_name) LIKE %s OR lower(a.department_name) LIKE %s
                   OR lower(a.clinician_name) LIKE %s OR lower(a.status) LIKE %s
                   OR lower(a.referral_priority) LIKE %s)
            ORDER BY a.appointment_date, a.appointment_time
            LIMIT %s
            """,
            (
                list(scopes),
                identifier,
                identifier,
                identifier,
                identifier,
                department_filter,
                department_filter,
                ward_filter,
                ward_filter,
                status_filter,
                status_filter,
                search,
                search,
                search,
                search,
                search,
                search,
                search,
                search,
                limit,
            ),
        )
        rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["table"] = row.pop("source_table", "appointments")
        return rows

    def _query_patients(self, cur, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        pattern = _like(_best_search_term(terms, stopwords))
        cur.execute(
            f"""
            SELECT p.patient_id, p.mrn, p.nhs_number, p.full_name, p.date_of_birth, p.ward_code,
                   w.ward_name, w.floor AS ward_floor, w.nurse_in_charge, w.phone AS ward_phone,
                   p.department_name, p.named_consultant, p.care_status, p.risk_flags, p.access_level
            FROM patients p
            LEFT JOIN wards w ON w.ward_code = p.ward_code
            WHERE {self._qualified_access_sql("p")}
              AND (%s = '%%' OR lower(p.full_name) LIKE %s OR lower(p.mrn) LIKE %s OR lower(p.nhs_number) LIKE %s)
            ORDER BY p.full_name
            LIMIT %s
            """,
            (list(scopes), pattern, pattern, pattern, pattern, limit),
        )
        return list(cur.fetchall())

    def _query_doctors(self, cur, query: str, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        pattern = _like(_best_search_term(terms, stopwords))
        on_call_only = "on call" in query.lower() or "on-call" in query.lower()
        cur.execute(
            f"""
            SELECT doctor_id, full_name, grade, specialty, department_name, phone,
                   email, bleep, on_call_today, access_level
            FROM doctors
            WHERE {self._access_sql()}
              AND (%s = false OR on_call_today = true)
              AND (%s = '%%' OR lower(full_name) LIKE %s OR lower(specialty) LIKE %s OR lower(department_name) LIKE %s)
            ORDER BY department_name, full_name
            LIMIT %s
            """,
            (list(scopes), on_call_only, "%" if on_call_only else pattern, pattern, pattern, pattern, limit),
        )
        return list(cur.fetchall())

    def _query_departments(self, cur, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        pattern = _like(_best_search_term(terms, stopwords))
        cur.execute(
            f"""
            SELECT department_id, department_name, specialty_group, location, main_phone,
                   email, service_lead, escalation_contact, access_level
            FROM departments
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(department_name) LIKE %s OR lower(specialty_group) LIKE %s)
            ORDER BY department_name
            LIMIT %s
            """,
            (list(scopes), pattern, pattern, pattern, limit),
        )
        return list(cur.fetchall())

    def _query_contacts(self, cur, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        pattern = _like(_best_search_term(terms, stopwords))
        cur.execute(
            f"""
            SELECT contact_id, contact_type, department_name, contact_name, role,
                   phone, email, available_hours, escalation_level, access_level
            FROM organization_contacts
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(contact_name) LIKE %s OR lower(department_name) LIKE %s
                   OR lower(contact_type) LIKE %s OR lower(role) LIKE %s)
            ORDER BY department_name, escalation_level
            LIMIT %s
            """,
            (list(scopes), pattern, pattern, pattern, pattern, pattern, limit),
        )
        return list(cur.fetchall())

    def _query_contact_information(
        self,
        cur,
        terms: list[str],
        scopes: tuple[str, ...],
        limit: int,
        stopwords: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        contact_stopwords = {
            "contact",
            "contacts",
            "call",
            "calling",
            "phone",
            "email",
            "reach",
            "info",
            "information",
            "how",
            "can",
            "for",
            "dr",
            "doctor",
            "doctors",
            "patient",
            "patients",
            "ward",
            "department",
        }
        pattern = _like(_best_search_term(terms, (stopwords or set()) | contact_stopwords))
        if pattern == "%%":
            pattern = _like(_best_search_term(terms, stopwords))
        rows: list[dict[str, Any]] = []
        person_terms = [
            term
            for term in terms
            if term not in contact_stopwords
            and term not in STOPWORDS
            and not re.fullmatch(r"(mrn)?\d{4,}|mrn\d+", term.lower())
        ][:4]
        doctor_requested = bool(set(terms) & {"dr", "doctor", "doctors", "consultant", "physician"})
        patient_requested = bool(set(terms) & {"patient", "patients", "mrn", "nhs"})
        person_name_requested = len(person_terms) >= 2

        def wrapped_rows(source_table: str, fetched: Sequence[dict[str, Any]], pk: str) -> list[dict[str, Any]]:
            wrapped: list[dict[str, Any]] = []
            for item in fetched:
                payload = dict(item)
                wrapped.append(
                    {
                        "source_table": source_table,
                        "source_filename": source_table,
                        "row_number": payload.get(pk),
                        "row": payload,
                        "access_level": payload.get("access_level"),
                    }
                )
            return wrapped

        def append_rows(source_table: str, fetched: Sequence[dict[str, Any]], pk: str) -> None:
            rows.extend(wrapped_rows(source_table, fetched, pk))

        def person_match_clause(column: str, query_terms: Sequence[str]) -> tuple[str, list[Any]]:
            if not query_terms:
                return f"lower({column}) LIKE %s", [pattern]
            parts = [f"lower({column}) LIKE %s" for _ in query_terms]
            return " AND ".join(parts), [_like(term) for term in query_terms]

        def fetch_doctors(row_limit: int) -> list[dict[str, Any]]:
            clause, params = person_match_clause("full_name", person_terms)
            cur.execute(
                f"""
                SELECT doctor_id, full_name, grade, specialty, department_name,
                       phone, email, bleep, on_call_today, access_level
                FROM doctors
                WHERE {self._access_sql()}
                  AND ({clause})
                ORDER BY full_name
                LIMIT %s
                """,
                (list(scopes), *params, max(1, row_limit)),
            )
            return wrapped_rows("doctors", list(cur.fetchall()), "doctor_id")

        def fetch_patients(row_limit: int) -> list[dict[str, Any]]:
            clause, params = person_match_clause("full_name", person_terms)
            cur.execute(
                f"""
                SELECT patient_id, mrn, full_name, ward_code, department_name,
                       named_consultant, care_status, access_level
                FROM patients
                WHERE {self._access_sql()}
                  AND ({clause})
                ORDER BY full_name
                LIMIT %s
                """,
                (list(scopes), *params, max(1, row_limit)),
            )
            return wrapped_rows("patients", list(cur.fetchall()), "patient_id")

        def fetch_staff_schedule(row_limit: int) -> list[dict[str, Any]]:
            clause, params = person_match_clause("staff_name", person_terms)
            cur.execute(
                f"""
                SELECT schedule_id, shift_date, department_name, role, staff_name,
                       shift_start, shift_end, on_call, contact, access_level
                FROM staff_schedule
                WHERE {self._access_sql()}
                  AND ({clause})
                ORDER BY shift_date, shift_start, staff_name
                LIMIT %s
                """,
                (list(scopes), *params, max(1, row_limit)),
            )
            return wrapped_rows("staff_schedule", list(cur.fetchall()), "schedule_id")

        if doctor_requested:
            doctor_rows = fetch_doctors(limit)
            if doctor_rows:
                return doctor_rows[:limit]
        if patient_requested:
            patient_rows = fetch_patients(limit)
            if patient_rows:
                return patient_rows[:limit]
        if person_name_requested:
            patient_rows = fetch_patients(limit)
            doctor_rows = fetch_doctors(limit)
            if patient_rows and not doctor_rows:
                return patient_rows[:limit]
            if doctor_rows and not patient_rows:
                return doctor_rows[:limit]
            if patient_rows or doctor_rows:
                return (patient_rows or doctor_rows)[:limit]
            staff_rows = fetch_staff_schedule(limit)
            if staff_rows:
                return staff_rows[:limit]

        cur.execute(
            f"""
            SELECT contact_id, contact_type, department_name, contact_name, role,
                   phone, email, available_hours, escalation_level, access_level
            FROM organization_contacts
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(department_name) LIKE %s OR lower(contact_type) LIKE %s
                   OR lower(role) LIKE %s OR lower(contact_name) LIKE %s)
            ORDER BY
              CASE WHEN lower(department_name) LIKE %s THEN 0 ELSE 1 END,
              escalation_level,
              contact_name
            LIMIT %s
            """,
            (list(scopes), pattern, pattern, pattern, pattern, pattern, pattern, max(1, limit)),
        )
        append_rows("organization_contacts", list(cur.fetchall()), "contact_id")

        if len(rows) < limit:
            cur.execute(
                f"""
                SELECT department_id, department_name, specialty_group, location, main_phone,
                       email, service_lead, escalation_contact, access_level
                FROM departments
                WHERE {self._access_sql()}
                  AND (%s = '%%' OR lower(department_name) LIKE %s OR lower(specialty_group) LIKE %s
                       OR lower(service_lead) LIKE %s)
                ORDER BY department_name
                LIMIT %s
                """,
                (list(scopes), pattern, pattern, pattern, pattern, max(1, limit - len(rows))),
            )
            append_rows("departments", list(cur.fetchall()), "department_id")

        if len(rows) < limit and not person_name_requested:
            cur.execute(
                f"""
                SELECT schedule_id, shift_date, department_name, role, staff_name,
                       shift_start, shift_end, on_call, contact, access_level
                FROM staff_schedule
                WHERE {self._access_sql()}
                  AND (%s = '%%' OR lower(staff_name) LIKE %s OR lower(role) LIKE %s
                       OR lower(department_name) LIKE %s OR lower(contact) LIKE %s)
                ORDER BY shift_date, shift_start, staff_name
                LIMIT %s
                """,
                (list(scopes), pattern, pattern, pattern, pattern, pattern, max(1, limit - len(rows))),
            )
            append_rows("staff_schedule", list(cur.fetchall()), "schedule_id")

        if len(rows) < limit:
            cur.execute(
                f"""
                SELECT ward_code, ward_name, department_name, floor, bed_capacity,
                       beds_available, nurse_in_charge, phone, access_level
                FROM wards
                WHERE {self._access_sql()}
                  AND (%s = '%%' OR lower(ward_code) LIKE %s OR lower(ward_name) LIKE %s
                       OR lower(department_name) LIKE %s OR lower(nurse_in_charge) LIKE %s)
                ORDER BY ward_name
                LIMIT %s
                """,
                (list(scopes), pattern, pattern, pattern, pattern, pattern, max(1, limit - len(rows))),
            )
            append_rows("wards", list(cur.fetchall()), "ward_code")

        return rows[:limit]

    def _query_appointments(self, cur, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        search_terms = _name_search_terms(terms, stopwords)
        mrn_terms = [term for term in terms if re.fullmatch(r"(mrn)?\d{4,}|mrn\d+", term.lower())]
        if mrn_terms:
            search_terms = mrn_terms
        if not search_terms:
            best_term = _best_search_term(terms, stopwords)
            search_terms = [best_term] if best_term else []

        where_parts = [self._qualified_access_sql("a")]
        params: list[Any] = [list(scopes)]
        if search_terms:
            for term in search_terms[:4]:
                pattern = _like(term)
                where_parts.append(
                    """
                    (
                        lower(a.patient_name) LIKE %s OR lower(a.patient_mrn) LIKE %s
                        OR lower(COALESCE(p.full_name, '')) LIKE %s
                        OR lower(COALESCE(p.patient_id, '')) LIKE %s
                        OR lower(COALESCE(p.nhs_number, '')) LIKE %s
                        OR lower(a.clinic_name) LIKE %s
                        OR lower(a.department_name) LIKE %s
                        OR lower(a.clinician_name) LIKE %s
                    )
                    """
                )
                params.extend([pattern] * 8)
        params.append(limit)
        cur.execute(
            f"""
            SELECT a.appointment_id, a.patient_mrn, a.patient_name, p.patient_id, p.nhs_number,
                   p.date_of_birth, p.ward_code, a.clinic_name, a.department_name,
                   a.appointment_date, a.appointment_time, a.clinician_name, a.status,
                   a.referral_priority, a.access_level
            FROM appointments a
            LEFT JOIN patients p ON p.mrn = a.patient_mrn
            WHERE {" AND ".join(where_parts)}
            ORDER BY a.appointment_date, a.appointment_time
            LIMIT %s
            """,
            tuple(params),
        )
        return list(cur.fetchall())

    def _query_wards(self, cur, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        pattern = _like(_best_search_term(terms, stopwords))
        cur.execute(
            f"""
            SELECT ward_code, ward_name, department_name, floor, bed_capacity,
                   beds_available, nurse_in_charge, phone, access_level
            FROM wards
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(ward_code) LIKE %s OR lower(ward_name) LIKE %s OR lower(department_name) LIKE %s)
            ORDER BY ward_code
            LIMIT %s
            """,
            (list(scopes), pattern, pattern, pattern, pattern, limit),
        )
        return list(cur.fetchall())

    def _query_formulary(self, cur, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        pattern = _like(_best_search_term(terms, stopwords))
        cur.execute(
            f"""
            SELECT medicine_id, medicine_name, category, restricted, approval_required,
                   max_adult_dose, monitoring_required, access_level
            FROM formulary
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(medicine_name) LIKE %s OR lower(category) LIKE %s)
            ORDER BY medicine_name
            LIMIT %s
            """,
            (list(scopes), pattern, pattern, pattern, limit),
        )
        return list(cur.fetchall())

    def _query_formulary_distinct_values(self, scopes: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
        legacy_distinct = getattr(self, "_query_uploaded_distinct_field_values", None)
        if callable(legacy_distinct):
            return legacy_distinct(
                scopes,
                ["medicine", "medicine_name", "drug"],
                source_filenames=["medication_formulary.csv"],
                limit=limit,
                output_field="medicine",
                fallback_markers=("medicine", "medication", "drug", "formulary"),
            )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT medicine_name, category
                    FROM formulary
                    WHERE {self._access_sql()}
                    ORDER BY medicine_name
                    LIMIT %s
                    """,
                    (list(scopes), limit),
                )
                return [
                    {
                        "source_table": "formulary",
                        "source_filename": "formulary",
                        "row_number": index,
                        "row": {"medicine": row["medicine_name"], "category": row.get("category")},
                        "access_level": "clinical",
                    }
                    for index, row in enumerate(cur.fetchall(), start=1)
                ]

    def _query_equipment(self, cur, terms: list[str], scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        legacy_lookup = getattr(self, "_query_uploaded_lookup_rows", None)
        if callable(legacy_lookup):
            return legacy_lookup(
                " ".join(terms),
                scopes,
                limit,
                source_filenames=["equipment_assets.csv"],
                stopwords=stopwords,
            )
        search_terms = _expanded_search_terms(" ".join(terms), stopwords or set())
        useful = [
            term
            for term in search_terms
            if term not in ROW_VALUE_GENERIC_QUERY_MARKERS and term not in ROW_VALUE_CONTEXT_STOPWORDS
        ]
        patterns = [_like(term) for term in (useful[:8] or [_best_search_term(terms, stopwords)])]
        search_where = " OR ".join(
            [
                "(lower(asset_id) LIKE %s OR lower(equipment_type) LIKE %s OR lower(location) LIKE %s OR lower(status) LIKE %s)"
                for _ in patterns
            ]
        )
        search_params = [value for pattern in patterns for value in (pattern, pattern, pattern, pattern)]
        cur.execute(
            f"""
            SELECT asset_id, equipment_type, location, status, last_service_date,
                   next_service_due, clinical_engineering_contact, access_level
            FROM equipment_assets
            WHERE {self._access_sql()}
              AND ({search_where})
            ORDER BY
              CASE WHEN lower(status) = 'available' THEN 0 ELSE 1 END,
              equipment_type,
              location
            LIMIT %s
            """,
            (list(scopes), *search_params, limit),
        )
        return list(cur.fetchall())

    def _query_equipment_distinct_values(self, scopes: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
        legacy_distinct = getattr(self, "_query_uploaded_distinct_field_values", None)
        if callable(legacy_distinct):
            return legacy_distinct(
                scopes,
                ["equipment_type", "asset_type", "device_type"],
                source_filenames=["equipment_assets.csv"],
                limit=limit,
                output_field="equipment_type",
                fallback_markers=("equipment", "asset", "device"),
            )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT equipment_type, count(*) AS row_count
                    FROM equipment_assets
                    WHERE {self._access_sql()}
                    GROUP BY equipment_type
                    ORDER BY equipment_type
                    LIMIT %s
                    """,
                    (list(scopes), limit),
                )
                return [
                    {
                        "source_table": "equipment_assets",
                        "source_filename": "equipment_assets",
                        "row_number": index,
                        "row": {"equipment_type": row["equipment_type"], "count": row["row_count"]},
                        "access_level": "all_staff",
                    }
                    for index, row in enumerate(cur.fetchall(), start=1)
                ]

    def _count_equipment(self, query: str, scopes: tuple[str, ...], stopwords: set[str] | None = None) -> int:
        legacy_count = getattr(self, "_count_uploaded_lookup_rows", None)
        if callable(legacy_count):
            counts = legacy_count(
                query,
                scopes,
                source_filenames=["equipment_assets.csv"],
                stopwords=stopwords,
            )
            return sum(int(value or 0) for value in counts.values())
        terms = _expanded_search_terms(query, stopwords or set())
        useful = [
            term
            for term in terms
            if term not in ROW_VALUE_GENERIC_QUERY_MARKERS and term not in ROW_VALUE_CONTEXT_STOPWORDS
        ]
        patterns = [_like(term) for term in (useful[:8] or [_best_search_term(_terms(query), stopwords)])]
        search_where = " OR ".join(
            [
                "(lower(asset_id) LIKE %s OR lower(equipment_type) LIKE %s OR lower(location) LIKE %s OR lower(status) LIKE %s)"
                for _ in patterns
            ]
        )
        search_params = [value for pattern in patterns for value in (pattern, pattern, pattern, pattern)]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT count(*) AS matching_rows
                    FROM equipment_assets
                    WHERE {self._access_sql()}
                      AND ({search_where})
                    """,
                    (list(scopes), *search_params),
                )
                row = cur.fetchone() or {}
                return int(row.get("matching_rows") or 0)

    def _query_directory(self, cur, primary: str, scopes: tuple[str, ...], limit: int, stopwords: set[str] | None = None):
        pattern = _like(primary if primary and primary not in (stopwords or set()) else "")
        cur.execute(
            f"""
            SELECT 'department' AS result_type, department_name AS name, service_lead AS role,
                   main_phone AS phone, email, access_level
            FROM departments
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(department_name) LIKE %s OR lower(service_lead) LIKE %s)
            UNION ALL
            SELECT 'contact' AS result_type, contact_name AS name, role, phone, email, access_level
            FROM organization_contacts
            WHERE {self._access_sql()}
              AND (%s = '%%' OR lower(contact_name) LIKE %s OR lower(role) LIKE %s OR lower(department_name) LIKE %s)
            ORDER BY result_type, name
            LIMIT %s
            """,
            (
                list(scopes),
                pattern,
                pattern,
                pattern,
                list(scopes),
                pattern,
                pattern,
                pattern,
                pattern,
                limit,
            ),
        )
        return list(cur.fetchall())
