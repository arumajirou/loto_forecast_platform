"""Command-line interface for read-only GitHub repository audits."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from loto.github_audit.core import DEFAULT_API_VERSION, classify_error, redact, safe_slug
from loto.github_audit.runner import AuditConfig, AuditRunner

DEFAULT_REPO = "arumajirou/loto_forecast_platform"


def self_test() -> int:
    assert classify_error("gh: HTTP 403: Forbidden", 1) == "BLOCKED"
    assert classify_error("gh: HTTP 404: Not Found", 1) == "NOT_AVAILABLE"
    assert classify_error("API rate limit exceeded", 1) == "RATE_LIMITED"
    assert classify_error("unclassified", 1) == "FAILED"
    assert redact({"token": "secret", "nested": {"password": "x"}, "name": "ok"}) == {
        "token": "<REDACTED>",
        "nested": {"password": "<REDACTED>"},
        "name": "ok",
    }
    assert safe_slug("owner/repo") == "owner-repo"
    print(json.dumps({"status": "PASS", "test": "github_audit_self_test"}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-github-audit",
        description=(
            "Export repository, issue, pull request, Actions, security, dependency, "
            "and settings evidence through authenticated read-only GitHub API calls."
        ),
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="repository in OWNER/REPO form")
    parser.add_argument(
        "--output-root",
        default="./github-audit-reports",
        help="parent directory for timestamped audit outputs",
    )
    parser.add_argument("--api-version", default=DEFAULT_API_VERSION)
    parser.add_argument(
        "--deep",
        action="store_true",
        help="inspect open PR/issue details and recent Actions job lists",
    )
    parser.add_argument("--max-items", type=int, default=5000)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--max-action-runs", type=int, default=500)
    parser.add_argument("--max-run-jobs", type=int, default=100)
    parser.add_argument("--max-pr-details", type=int, default=200)
    parser.add_argument("--max-issue-details", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--duplicate-threshold", type=float, default=0.90)
    parser.add_argument("--self-test", action="store_true")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    for name in (
        "max_items",
        "max_pages",
        "max_action_runs",
        "max_run_jobs",
        "max_pr_details",
        "max_issue_details",
        "timeout",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if not 0.0 <= args.duplicate_threshold <= 1.0:
        parser.error("--duplicate-threshold must be between 0 and 1")
    if args.repo.count("/") != 1:
        parser.error("--repo must use OWNER/REPO form")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return self_test()
    config = AuditConfig(
        repo=args.repo,
        output_root=Path(args.output_root),
        api_version=args.api_version,
        deep=args.deep,
        max_items=args.max_items,
        max_pages=args.max_pages,
        max_action_runs=args.max_action_runs,
        max_run_jobs=args.max_run_jobs,
        max_pr_details=args.max_pr_details,
        max_issue_details=args.max_issue_details,
        timeout=args.timeout,
        duplicate_threshold=args.duplicate_threshold,
    )
    try:
        summary = AuditRunner(config).collect()
    except KeyboardInterrupt:
        print(json.dumps({"status": "INTERRUPTED"}, ensure_ascii=False))
        return 130
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            )
        )
        traceback.print_exc(file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return int(summary.get("exit_code", 1))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
