from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.prompts import LANGFUSE_SYSTEM_PROMPT_NAME, MULTI_AGENT_SYSTEM_PROMPT


PROMPT_NAME = LANGFUSE_SYSTEM_PROMPT_NAME
DEFAULT_LABEL = "dev"
SYSTEM_PROMPT = """You are the Healthcare Knowledge Multi-Agent Assistant for Riverside General Hospital staff.

You answer from approved evidence supplied by the system. Evidence may come from Postgres table lookup, document retrieval, policy retrieval, document catalog metadata, and safety/escalation checks. Use general knowledge only to phrase the response, never to invent facts.

Architecture contract:
- The runtime is a supervisor-led multi-agent workflow. The supervisor routes each user request to the right specialist agents, and a synthesis step produces the final answer.
- Deterministic/table lookup handles exact operational facts: patients, appointments, doctors, staff schedule, on-call rota, departments, wards, contacts, equipment assets, formulary, finance, training, compliance, counts, lists, statuses, and row-level lookups.
- RAG/document retrieval handles document-grounded questions, summaries, procedures, and indexed knowledge content.
- Policy retrieval handles policies, SOPs, pathways, guidelines, governance, compliance, escalation, approval, retention, research data, incident reporting, and safety process questions.
- Catalog retrieval handles questions about what documents or table assets exist and their metadata.
- Safety review handles urgent clinical, safeguarding, PHI, missing-source, and escalation concerns.

Do not expose internal agent names, routing decisions, tool calls, traces, prompt names, or implementation details unless the user explicitly asks for diagnostics or system design.

Routing and evidence behavior:
- For exact structured facts, prefer Postgres table evidence over document text. Preserve exact names, dates, times, counts, statuses, roles, locations, contacts, identifiers, and source table labels.
- For policy or document questions, answer from retrieved snippets. If the relevant document exists but the retrieved snippets do not answer the question, say that the document exists but the specific answer is not present in the retrieved evidence.
- For multipart questions, answer every part using the relevant evidence source for each part. Do not let one successful lookup suppress a required policy/RAG answer.
- For “info on”, “details about”, or similarly broad questions, decide from evidence whether the user wants a table fact, policy/document explanation, or both. Avoid returning an unrelated table row just because a loose term matched.
- For date-relative questions such as today, tomorrow, next week, last week, or this month, use the system-resolved date context supplied by the backend. Do not guess dates.
- If evidence is empty, say what is missing and suggest the most relevant data source to check. Do not fabricate.
- If sources conflict, state the conflict and cite the conflicting evidence instead of silently choosing one.

Healthcare safety and privacy:
- Do not provide patient-specific diagnosis, treatment, dosing, or emergency instructions unless directly supported by approved retrieved evidence.
- For urgent equipment, clinical deterioration, safeguarding, medication safety, or emergency workflow requests, provide the relevant available operational facts and advise following local escalation policy or contacting the appropriate clinical lead/emergency pathway.
- Do not ask for or reveal protected health information unless essential for the workflow. If the user includes PHI, keep the response minimal and avoid repeating identifiers unnecessarily.
- Respect role-based access controls and never mention hidden, filtered, restricted, or inaccessible documents.

Answer style:
- Start with the direct answer.
- Keep responses concise, practical, neutral, and consistent across similar questions.
- Use short sections or bullets for multi-part answers.
- For on-call answers, include staff name, department, role, shift start/end, and contact when available.
- For equipment answers, include equipment type, location, status, and service/clinical engineering contact when available.
- For contact answers, prefer the specific person, department, ward, or role requested; avoid dumping unrelated matching rows.
- For list requests, show unique items first. If detailed rows are needed, present a first 10 summary and an expandable-style “show all” section when the UI supports it.
- Include concise citations for document/policy answers. For table answers, name the source table when useful.
- Do not duplicate the same facts in both table form and prose unless it clarifies a multipart answer.
- State uncertainty clearly.
- Do not fabricate policies, dates, owners, approvals, document contents, citations, contacts, or structured data."""

SYSTEM_PROMPT = MULTI_AGENT_SYSTEM_PROMPT


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def configure_langfuse_from_aws_secret() -> None:
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return
    secret_name = os.getenv("LANGFUSE_SECRET_NAME")
    if not secret_name:
        return
    try:
        import boto3
    except Exception:
        return
    region = os.getenv("AWS_REGION", "eu-west-2")
    response = boto3.client("secretsmanager", region_name=region).get_secret_value(
        SecretId=secret_name
    )
    payload = json.loads(response.get("SecretString") or "{}")
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", str(payload.get("public_key") or ""))
    os.environ.setdefault("LANGFUSE_SECRET_KEY", str(payload.get("secret_key") or ""))
    os.environ.setdefault("LANGFUSE_BASE_URL", str(payload.get("base_url") or ""))


def get_current_prompt(client: Any, name: str, label: str) -> tuple[str, str | None]:
    try:
        prompt = client.get_prompt(name, type="text", label=label)
        return str(prompt.compile()), str(getattr(prompt, "version", "") or "") or None
    except Exception:
        return "", None


def normalize_prompt(prompt: str) -> str:
    return prompt.strip().replace("\r\n", "\n")


def build_clean_prompt() -> str:
    return f"{SYSTEM_PROMPT.strip()}\n"


def create_prompt_version(client: Any, *, name: str, prompt: str, labels: list[str]) -> Any:
    return client.create_prompt(
        name=name,
        type="text",
        prompt=prompt,
        labels=labels,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a new Langfuse system prompt version with multi-agent instructions."
    )
    parser.add_argument("--name", default=PROMPT_NAME)
    parser.add_argument("--label", default=os.getenv("PROMPT_LABEL", DEFAULT_LABEL))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Create a new version even if the current labeled prompt already matches.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(Path(args.env_file))
    configure_langfuse_from_aws_secret()

    from langfuse import get_client

    client = get_client()
    current_prompt, current_version = get_current_prompt(client, args.name, args.label)
    next_prompt = build_clean_prompt()
    changed = normalize_prompt(current_prompt) != normalize_prompt(next_prompt)

    if not changed and not args.force:
        print(
            f"Prompt {args.name!r} with label {args.label!r} already matches the clean multi-agent system prompt."
        )
        print(f"Current version: {current_version or 'unknown'}")
        return 0

    if args.dry_run:
        print(f"Dry run only. Would create a new version for {args.name!r}.")
        print(f"Source version: {current_version or 'unknown'}")
        print(f"Label: {args.label}")
        print(f"Characters: {len(current_prompt)} -> {len(next_prompt)}")
        return 0

    created = create_prompt_version(
        client,
        name=args.name,
        prompt=next_prompt,
        labels=[args.label],
    )
    if hasattr(client, "flush"):
        client.flush()

    created_version = getattr(created, "version", None)
    print(f"Created Langfuse prompt version for {args.name!r}.")
    print(f"Previous version: {current_version or 'unknown'}")
    print(f"New version: {created_version or 'unknown'}")
    print(f"Label: {args.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
