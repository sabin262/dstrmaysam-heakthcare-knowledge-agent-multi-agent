from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import DEFAULT_DATASET_ID, load_bundled_dataset, load_dataset
from .evaluator import EvaluationRunner, HttpChatClient
from .reporting import markdown_report
from .schema import summarize_results


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
    args = parser.parse_args()

    cases = load_dataset(args.dataset_path) if args.dataset_path else load_bundled_dataset(args.dataset_id)
    categories = {str(category).strip() for category in args.category if str(category).strip()}
    if categories:
        cases = [case for case in cases if case.category in categories]
    if args.limit:
        cases = cases[: args.limit]

    client = HttpChatClient(base_url=args.api_url, username=args.username, password=args.password)
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
