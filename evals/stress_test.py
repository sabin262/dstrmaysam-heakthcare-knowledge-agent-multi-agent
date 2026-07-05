from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from collections import defaultdict
from typing import Any


BASE_CASES = [
    {
        "question": "Does Leo Bennett have any appointments?",
        "expected_sources": ["appointments", "patients"],
        "expected_tools": ["postgres_deterministic_lookup"],
    },
    {
        "question": "Show patient details for MRN10006.",
        "expected_sources": ["patients", "wards"],
        "expected_tools": ["postgres_deterministic_lookup"],
    },
    {
        "question": "Leo Bennett is in which ward?",
        "expected_sources": ["patients", "wards"],
        "expected_tools": ["postgres_deterministic_lookup"],
    },
    {
        "question": "Who is on call on 2026-06-29?",
        "expected_sources": ["staff_schedule"],
        "expected_tools": ["postgres_deterministic_lookup", "calendar_rota_lookup"],
    },
    {
        "question": "Is anybody from Radiology on call on 2026-06-29?",
        "expected_sources": ["staff_schedule"],
        "expected_tools": ["postgres_deterministic_lookup", "calendar_rota_lookup"],
    },
    {
        "question": "What is the phone number for ICU outreach?",
        "expected_sources": ["organization_contacts"],
        "expected_tools": ["postgres_deterministic_lookup"],
    },
    {
        "question": "Is vancomycin restricted locally?",
        "expected_sources": ["formulary"],
        "expected_tools": ["formulary_table_lookup", "postgres_deterministic_lookup"],
    },
    {
        "question": "How many ventilators are there and how many of them are working?",
        "expected_sources": ["equipment_assets"],
        "expected_tools": ["postgres_deterministic_lookup", "table_lookup"],
    },
    {
        "question": "Which medicines need approval locally?",
        "expected_sources": ["formulary"],
        "expected_tools": ["formulary_table_lookup", "postgres_deterministic_lookup"],
    },
    {
        "question": "What is the Cardiology department phone number?",
        "expected_sources": ["departments"],
        "expected_tools": ["postgres_deterministic_lookup"],
    },
    {
        "question": "What is the phone number for Radiology urgent report?",
        "expected_sources": ["organization_contacts"],
        "expected_tools": ["postgres_deterministic_lookup"],
    },
    {
        "question": "Where is ward W07?",
        "expected_sources": ["wards"],
        "expected_tools": ["postgres_deterministic_lookup"],
    },
    {
        "question": "How do I report an incident?",
        "expected_sources": ["RGH-POL-011_Incident_Reporting_and_Data_Breach_Response_Policy.pdf"],
        "expected_tools": ["policy_search"],
    },
    {
        "question": "How should I handle research data?",
        "expected_sources": ["RGH-POL-013_Research_Data_Access_and_De_identification_Policy.pdf"],
        "expected_tools": ["policy_search"],
    },
    {
        "question": "How long is patient data stored?",
        "expected_sources": ["RGH-POL-006_Data_Retention_and_Records_Management_Policy.pdf"],
        "expected_tools": ["policy_search"],
    },
    {
        "question": "What does the IoT data integration policy say about device governance?",
        "expected_sources": ["RGH-POL-015_Medical_Device_and_IoT_Data_Integration_Policy.pdf"],
        "expected_tools": ["policy_search", "document_search", "rag_search"],
    },
    {
        "question": "What policies do we have?",
        "expected_sources": ["document_catalog"],
        "expected_tools": ["catalogue_search", "document_catalog"],
    },
    {
        "question": "What general documents do we have?",
        "expected_sources": ["document_catalog"],
        "expected_tools": ["catalogue_search", "document_catalog"],
    },
    {
        "question": "What does the leave guideline say about leave procedure?",
        "expected_sources": ["hr_guideline_attendance_leave_flexible_working_and_rostering.pdf"],
        "expected_tools": ["policy_search", "document_search", "rag_search"],
    },
    {
        "question": "What is the policy regarding MRN10006?",
        "expected_sources": ["safety_guard"],
        "expected_tools": ["safety_guard"],
    },
]

PARAPHRASES = [
    "{q}",
    "Can you answer this using the right healthcare data source: {q}",
    "Give me the current operational or policy answer for: {q}",
    "What source supports the answer to: {q}",
    "Please answer using Postgres tables or approved indexed documents: {q}",
]


def post_chat(api_url: str, token: str, question: str) -> dict[str, Any]:
    body = json.dumps({"query": question}).encode("utf-8")
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/chat",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def token_set(text: str) -> set[str]:
    return {term.lower().strip(".,;:!?()[]") for term in text.split() if len(term) > 3}


def jaccard(left: str, right: str) -> float:
    a = token_set(left)
    b = token_set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def source_text(source: dict[str, Any]) -> str:
    values = [
        source.get("uri"),
        source.get("source"),
        source.get("source_table"),
        source.get("title"),
        source.get("filename"),
        source.get("document_name"),
    ]
    metadata = source.get("metadata")
    if isinstance(metadata, dict):
        values.extend(
            [
                metadata.get("source_table"),
                metadata.get("source"),
                metadata.get("title"),
                metadata.get("filename"),
                metadata.get("document_name"),
            ]
        )
    return " ".join(str(value).lower() for value in values if value)


def source_match(sources: list[dict[str, Any]], expected_sources: list[str]) -> bool:
    if not expected_sources:
        return True
    haystack = " ".join(source_text(source) for source in sources)
    return any(expected.lower() in haystack for expected in expected_sources)


def tool_match(tools_used: list[Any], expected_tools: list[str]) -> bool:
    if not expected_tools:
        return True
    actual = {str(tool).lower() for tool in tools_used}
    return any(expected.lower() in actual for expected in expected_tools)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 100-query AWS source consistency stress test")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--output", default="stress_report.json")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for case in BASE_CASES:
        base = case["question"]
        for template in PARAPHRASES:
            query = template.format(q=base)
            started = time.perf_counter()
            try:
                response = post_chat(args.api_url, args.token, query)
                error = None
            except Exception as exc:
                response = {"answer": "", "sources": [], "tools_used": []}
                error = str(exc)
            sources = response.get("sources", []) or []
            tools_used = response.get("tools_used", []) or []
            rows.append(
                {
                    "base_question": base,
                    "query": query,
                    "answer": response.get("answer", ""),
                    "sources": sources,
                    "tools_used": tools_used,
                    "expected_sources": case.get("expected_sources", []),
                    "expected_tools": case.get("expected_tools", []),
                    "expected_source_match": source_match(sources, case.get("expected_sources", [])),
                    "expected_tool_match": tool_match(tools_used, case.get("expected_tools", [])),
                    "input_tokens": response.get("input_tokens", 0),
                    "output_tokens": response.get("output_tokens", 0),
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "error": error,
                }
            )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["base_question"]].append(row)

    consistency = {}
    for question, group in grouped.items():
        anchor = group[0]["answer"]
        similarities = [jaccard(anchor, row["answer"]) for row in group[1:]]
        source_sets = [
            {source.get("uri") or source.get("source_table") for source in row["sources"] if source.get("uri") or source.get("source_table")}
            for row in group
        ]
        source_overlap = 0.0
        if source_sets and source_sets[0]:
            source_overlap = sum(
                len(source_sets[0] & source_set) / len(source_sets[0])
                for source_set in source_sets[1:]
            ) / max(1, len(source_sets) - 1)
        consistency[question] = {
            "avg_answer_similarity": statistics.mean(similarities) if similarities else 1.0,
            "source_overlap": source_overlap,
            "errors": sum(1 for row in group if row["error"]),
            "expected_source_match_rate": sum(1 for row in group if row["expected_source_match"]) / len(group),
            "expected_tool_match_rate": sum(1 for row in group if row["expected_tool_match"]) / len(group),
        }

    latencies = [row["latency_ms"] for row in rows]
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_queries": len(rows),
        "failed_queries": sum(1 for row in rows if row["error"]),
        "expected_source_misses": sum(1 for row in rows if not row["expected_source_match"]),
        "expected_tool_misses": sum(1 for row in rows if not row["expected_tool_match"]),
        "latency_ms": {
            "min": min(latencies) if latencies else 0,
            "max": max(latencies) if latencies else 0,
            "avg": statistics.mean(latencies) if latencies else 0,
        },
        "consistency": consistency,
        "rows": rows,
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "total_queries",
                    "failed_queries",
                    "expected_source_misses",
                    "expected_tool_misses",
                    "latency_ms",
                ]
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
