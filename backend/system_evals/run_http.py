from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .dataset import DEFAULT_DATASET_ID, load_bundled_dataset, load_dataset
from .evaluator import EvaluationRunner, HttpChatClient
from .reporting import markdown_report
from .schema import summarize_results


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Run system-level golden dataset evals against a live /chat API.")
    parser.add_argument("--api-url", required=True, help="Backend API base URL, for example http://localhost:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--dataset-path", default="")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--timeout-seconds", type=int, default=_env_int("SYSTEM_EVAL_TIMEOUT_SECONDS", 120))
    parser.add_argument("--retry-attempts", type=int, default=_env_int("SYSTEM_EVAL_RETRY_ATTEMPTS", 4))
    parser.add_argument(
        "--retry-initial-seconds",
        type=float,
        default=_env_float("SYSTEM_EVAL_RETRY_INITIAL_SECONDS", 1.0),
    )
    parser.add_argument(
        "--retry-max-seconds",
        type=float,
        default=_env_float("SYSTEM_EVAL_RETRY_MAX_SECONDS", 20.0),
    )
    args = parser.parse_args()

    cases = load_dataset(args.dataset_path) if args.dataset_path else load_bundled_dataset(args.dataset_id)
    categories = {str(category).strip() for category in args.category if str(category).strip()}
    if categories:
        cases = [case for case in cases if case.category in categories]
    if args.limit:
        cases = cases[: args.limit]

    client = HttpChatClient(
        base_url=args.api_url,
        username=args.username,
        password=args.password,
        timeout_seconds=args.timeout_seconds,
        retry_attempts=args.retry_attempts,
        retry_initial_seconds=args.retry_initial_seconds,
        retry_max_seconds=args.retry_max_seconds,
    )
    results = EvaluationRunner(client).run(cases)
    summary = summarize_results(args.dataset_id, results)
    payload = {
        "summary": summary.as_dict(),
        "cases": [result.as_dict() for result in results],
    }
    report = markdown_report(run_id="http-run", summary=summary, results=results)

    if args.json_output:
        Path(args.json_output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(report, encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return 0 if summary.failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
