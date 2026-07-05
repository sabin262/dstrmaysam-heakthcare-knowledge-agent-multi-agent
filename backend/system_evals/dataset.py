from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import EvaluationCase


DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DATASET_ID = "system_golden_v1"


def bundled_dataset_ids() -> list[str]:
    return sorted(path.stem for path in DATA_DIR.glob("*.yaml"))


def load_bundled_dataset(dataset_id: str = DEFAULT_DATASET_ID) -> list[EvaluationCase]:
    safe_id = "".join(ch for ch in dataset_id if ch.isalnum() or ch in {"_", "-"}).strip()
    if not safe_id:
        raise ValueError("dataset_id is required")
    return load_dataset(DATA_DIR / f"{safe_id}.yaml")


def load_dataset(path: str | Path) -> list[EvaluationCase]:
    raw = Path(path).read_text(encoding="utf-8")
    payload = _loads_yamlish(raw)
    defaults: dict[str, Any] = {}
    if isinstance(payload, dict):
        raw_defaults = payload.get("defaults", {})
        if isinstance(raw_defaults, dict):
            defaults = dict(raw_defaults)
        cases_payload = payload.get("cases", [])
    else:
        cases_payload = payload
    if not isinstance(cases_payload, list):
        raise ValueError("Evaluation dataset must contain a cases list")
    cases = [
        EvaluationCase.from_dict({**defaults, **item})
        for item in cases_payload
        if isinstance(item, dict)
    ]
    seen: set[str] = set()
    for case in cases:
        case.validate()
        if case.id in seen:
            raise ValueError(f"Duplicate evaluation case id: {case.id}")
        seen.add(case.id)
    return cases


def _loads_yamlish(raw: str) -> Any:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(raw)
    except Exception:
        return json.loads(raw)
