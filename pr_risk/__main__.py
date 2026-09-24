"""CLI: python -m pr_risk --pr-url ... | --diff-file ... | --github-event"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from pr_risk.classify import classify_files
from pr_risk.github_api import apply_result, fetch_pr_files, load_github_event, parse_pr_url
from pr_risk.parse import parse_unified_diff
from pr_risk.policy import REVIEW_MEANING
from pr_risk.types import RiskResult

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
SAMPLE_FILES = {
    "query": SAMPLES_DIR / "query_change.diff",
    "endpoint": SAMPLES_DIR / "new_endpoint.diff",
    "css": SAMPLES_DIR / "css_button.diff",
}


def result_as_dict(result: RiskResult) -> dict:
    return {
        "tier": result.tier,
        "bumped_for_low_confidence": result.bumped_for_low_confidence,
        "review": REVIEW_MEANING[result.tier],
        "reasons": [
            {
                "file": reason.file,
                "signal": reason.signal,
                "probability": reason.probability,
            }
            for reason in result.reasons
        ],
    }


def print_result(result: RiskResult, as_json: bool) -> None:
    payload = result_as_dict(result)
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    print(f"tier: {result.tier}")
    print(f"review: {REVIEW_MEANING[result.tier]}")
    if result.bumped_for_low_confidence:
        print("note: raised one tier because a deciding signal had low confidence")
    print("reasons:")
    for reason in result.reasons:
        print(f"  {reason.file}  {reason.signal}  {reason.probability:.3f}")


def require_typesafe_key(*, github_event: bool) -> bool:
    if os.environ.get("TYPESAFE_API_KEY"):
        return True
    message = (
        "TYPESAFE_API_KEY is not set. Add the repo secret TYPESAFE_API_KEY "
        "to enable PR risk classification. Skipping without failing the PR."
        if github_event
        else "TYPESAFE_API_KEY is required. Export it or add it to .env (see .env.example)."
    )
    print(message, file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Classify PR merge risk with Jev (TypeSafe) plus path rules."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pr-url", help="GitHub pull request URL")
    source.add_argument("--diff-file", help="Path to a unified diff")
    source.add_argument(
        "--github-event",
        action="store_true",
        help="Read GITHUB_EVENT_PATH and apply labels/comment (CI)",
    )
    source.add_argument(
        "--sample",
        choices=sorted(SAMPLE_FILES),
        help="Classify a fixture from pr_risk/samples/",
    )
    parser.add_argument("--title", default="", help="PR title (diff-file / sample)")
    parser.add_argument("--body", default="", help="PR body (diff-file / sample)")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument(
        "--apply-github",
        action="store_true",
        help="With --pr-url, write the label and sticky comment",
    )
    args = parser.parse_args(argv)

    github_event = bool(args.github_event)
    if not require_typesafe_key(github_event=github_event):
        return 0 if github_event else 1

    if args.diff_file or args.sample:
        path = SAMPLE_FILES[args.sample] if args.sample else Path(args.diff_file)
        files = parse_unified_diff(path.read_text(encoding="utf-8"))
        result = classify_files(files, pr_title=args.title, pr_body=args.body)
        print_result(result, args.json)
        return 0

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required to read the pull request.", file=sys.stderr)
        return 1

    if args.pr_url:
        owner, repo, number = parse_pr_url(args.pr_url)
        title, body, files = fetch_pr_files(owner, repo, number, token)
        result = classify_files(files, pr_title=title, pr_body=body)
        print_result(result, args.json)
        if args.apply_github:
            apply_result(owner, repo, number, token, result)
        return 0

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("GITHUB_EVENT_PATH is not set.", file=sys.stderr)
        return 1
    owner, repo, number, title, body = load_github_event(event_path)
    _event_title, _event_body, files = fetch_pr_files(owner, repo, number, token)
    result = classify_files(files, pr_title=title, pr_body=body)
    print_result(result, args.json)
    apply_result(owner, repo, number, token, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
