"""Artifact generation for GitHub repository audits."""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
import zipfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence

from loto.github_audit.core import GhClient, iso_now, sha256_file, write_json

UTC = dt.timezone.utc


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else value


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fields})


def _parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _verified_count(client: GhClient, name: str) -> int | str:
    value = client.datasets.get(name)
    if isinstance(value, list):
        return len(value)
    return f"UNKNOWN:{client.status_for(name) or 'NOT_REQUESTED'}"


def _normalise_title(title: str) -> str:
    text = title.lower()
    text = re.sub(r"#\d+", "", text)
    text = re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff]+", " ", text)
    return " ".join(text.split())


def _duplicate_issue_rows(
    issue_rows: list[dict[str, Any]], threshold: float
) -> list[dict[str, Any]]:
    open_rows = [row for row in issue_rows if row["state"] == "open"]
    candidates = []
    for index, left in enumerate(open_rows):
        left_title = _normalise_title(str(left.get("title") or ""))
        if not left_title:
            continue
        for right in open_rows[index + 1 :]:
            right_title = _normalise_title(str(right.get("title") or ""))
            similarity = SequenceMatcher(None, left_title, right_title).ratio()
            if similarity >= threshold:
                candidates.append(
                    {
                        "issue_a": left["number"],
                        "issue_b": right["number"],
                        "similarity": round(similarity, 4),
                        "title_a": left["title"],
                        "title_b": right["title"],
                    }
                )
    return sorted(candidates, key=lambda item: item["similarity"], reverse=True)


def _write_pr_stack(path: Path, rows: list[dict[str, Any]], default_branch: str) -> None:
    lines = [
        "digraph pull_request_stack {",
        '  rankdir="LR";',
        '  node [shape=box, fontname="Arial"];',
        f'  "{default_branch}" [shape=oval];',
    ]
    head_to_number = {
        str(row["head_ref"]): row["number"]
        for row in rows
        if row["state"] == "open" and row.get("head_ref")
    }
    for row in rows:
        if row["state"] != "open":
            continue
        number = row["number"]
        title = str(row.get("title") or "").replace('"', r'\"')[:80]
        readiness = "Draft" if row.get("draft") else "Ready"
        lines.append(f'  "PR#{number}" [label="PR #{number}\\n{readiness}\\n{title}"];')
        base_ref = str(row.get("base_ref") or default_branch)
        parent = f"PR#{head_to_number[base_ref]}" if base_ref in head_to_number else base_ref
        lines.append(f'  "{parent}" -> "PR#{number}";')
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_tables(
    client: GhClient, run_dir: Path, duplicate_threshold: float
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tables = run_dir / "tables"
    repository = client.datasets.get("repository") or {}
    issues = client.datasets.get("issues") or []
    pulls = client.datasets.get("pulls") or []
    workflows = client.datasets.get("workflows") or []
    runs = client.datasets.get("workflow_runs") or []
    branches = client.datasets.get("branches") or []

    issue_rows = [
        {
            "number": item.get("number"),
            "state": item.get("state"),
            "state_reason": item.get("state_reason"),
            "title": item.get("title"),
            "author": (item.get("user") or {}).get("login"),
            "assignees": [value.get("login") for value in item.get("assignees", [])],
            "labels": [value.get("name") for value in item.get("labels", [])],
            "comments": item.get("comments"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "closed_at": item.get("closed_at"),
            "html_url": item.get("html_url"),
        }
        for item in issues
    ]
    _write_csv(
        tables / "issues.csv",
        issue_rows,
        (
            "number",
            "state",
            "state_reason",
            "title",
            "author",
            "assignees",
            "labels",
            "comments",
            "created_at",
            "updated_at",
            "closed_at",
            "html_url",
        ),
    )

    now = dt.datetime.now(UTC)
    pr_rows = []
    for item in pulls:
        updated = _parse_datetime(item.get("updated_at"))
        base_ref = (item.get("base") or {}).get("ref")
        pr_rows.append(
            {
                "number": item.get("number"),
                "state": item.get("state"),
                "draft": item.get("draft"),
                "merged_at": item.get("merged_at"),
                "title": item.get("title"),
                "author": (item.get("user") or {}).get("login"),
                "base_ref": base_ref,
                "head_ref": (item.get("head") or {}).get("ref"),
                "head_sha": (item.get("head") or {}).get("sha"),
                "stacked_on_non_default": bool(
                    base_ref and base_ref != repository.get("default_branch")
                ),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "age_since_update_days": (now - updated).days if updated else None,
                "html_url": item.get("html_url"),
            }
        )
    _write_csv(
        tables / "pull_requests.csv",
        pr_rows,
        (
            "number",
            "state",
            "draft",
            "merged_at",
            "title",
            "author",
            "base_ref",
            "head_ref",
            "head_sha",
            "stacked_on_non_default",
            "created_at",
            "updated_at",
            "age_since_update_days",
            "html_url",
        ),
    )

    workflow_rows = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "path": item.get("path"),
            "state": item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "html_url": item.get("html_url"),
        }
        for item in workflows
    ]
    _write_csv(
        tables / "workflows.csv",
        workflow_rows,
        ("id", "name", "path", "state", "created_at", "updated_at", "html_url"),
    )

    run_rows = []
    for item in runs:
        created = _parse_datetime(item.get("created_at"))
        updated = _parse_datetime(item.get("updated_at"))
        run_rows.append(
            {
                "id": item.get("id"),
                "run_number": item.get("run_number"),
                "run_attempt": item.get("run_attempt"),
                "name": item.get("name"),
                "event": item.get("event"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "head_branch": item.get("head_branch"),
                "head_sha": item.get("head_sha"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "duration_seconds": (
                    round((updated - created).total_seconds(), 3)
                    if created and updated
                    else None
                ),
                "actor": (item.get("actor") or {}).get("login"),
                "html_url": item.get("html_url"),
            }
        )
    _write_csv(
        tables / "workflow_runs.csv",
        run_rows,
        (
            "id",
            "run_number",
            "run_attempt",
            "name",
            "event",
            "status",
            "conclusion",
            "head_branch",
            "head_sha",
            "created_at",
            "updated_at",
            "duration_seconds",
            "actor",
            "html_url",
        ),
    )

    _write_csv(
        tables / "branches.csv",
        [
            {
                "name": item.get("name"),
                "protected": item.get("protected"),
                "sha": (item.get("commit") or {}).get("sha"),
            }
            for item in branches
        ],
        ("name", "protected", "sha"),
    )
    _write_csv(
        tables / "endpoint_status.csv",
        [record.to_dict() for record in client.records],
        (
            "name",
            "endpoint",
            "status",
            "ok",
            "count",
            "duration_ms",
            "fetched_at",
            "returncode",
            "error",
            "raw_file",
        ),
    )

    job_rows = client.datasets.get("action_job_rows") or []
    _write_csv(
        tables / "action_run_jobs.csv",
        job_rows,
        (
            "run_id",
            "run_number",
            "name",
            "event",
            "status",
            "conclusion",
            "created_at",
            "updated_at",
            "jobs_status",
            "job_count",
            "zero_jobs",
            "html_url",
        ),
    )

    security_rows = []
    for alert_type, dataset_name in (
        ("dependabot", "dependabot_alerts_open"),
        ("code_scanning", "code_scanning_alerts_open"),
        ("secret_scanning", "secret_scanning_alerts_open"),
    ):
        values = client.datasets.get(dataset_name)
        if not isinstance(values, list):
            continue
        for item in values:
            security_rows.append(
                {
                    "alert_type": alert_type,
                    "number": item.get("number"),
                    "state": item.get("state"),
                    "severity": (
                        (item.get("security_advisory") or {}).get("severity")
                        or (item.get("rule") or {}).get("security_severity_level")
                        or item.get("secret_type_display_name")
                    ),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "html_url": item.get("html_url"),
                }
            )
    _write_csv(
        tables / "security_alerts.csv",
        security_rows,
        ("alert_type", "number", "state", "severity", "created_at", "updated_at", "html_url"),
    )

    duplicate_rows = _duplicate_issue_rows(issue_rows, duplicate_threshold)
    _write_csv(
        tables / "possible_duplicate_issues.csv",
        duplicate_rows,
        ("issue_a", "issue_b", "similarity", "title_a", "title_b"),
    )
    _write_pr_stack(
        tables / "pr_stack.dot",
        pr_rows,
        str(repository.get("default_branch") or "main"),
    )
    return {
        "issue_rows": issue_rows,
        "pr_rows": pr_rows,
        "workflow_rows": workflow_rows,
        "run_rows": run_rows,
        "job_rows": job_rows,
        "duplicate_rows": duplicate_rows,
    }, security_rows


def _markdown(summary: dict[str, Any], client: GhClient) -> str:
    repo = summary["repository"]
    prs = summary["pull_requests"]
    actions = summary["actions"]
    security = summary["security"]
    lines = [
        "# GitHub Repository Audit Report",
        "",
        f"- Repository: `{summary['repo']}`",
        f"- Status: **{summary['status']}**",
        f"- Generated: `{summary['finished_at']}`",
        f"- REST API version: `{summary['api_version']}`",
        f"- Deep inspection: `{summary['deep']}`",
        "",
        "## Executive summary",
        "",
        f"- Visibility: `{repo.get('visibility')}`",
        f"- Default branch: `{repo.get('default_branch')}`",
        f"- Default branch HEAD: `{summary['head'].get('sha') or 'UNKNOWN'}`",
        f"- Combined commit status: `{summary['head'].get('combined_status') or 'UNKNOWN'}`",
        f"- Open issues: `{summary['issues']['open']}`",
        f"- Open PRs: `{prs['open']}`",
        f"- Draft PRs: `{prs['open_draft']}`",
        f"- Stacked PRs: `{prs['open_stacked']}`",
        f"- Workflows: `{actions['workflow_count']}`",
        f"- Workflow runs exported: `{actions['run_count_exported']}`",
        f"- Zero-job runs inspected: `{actions['zero_job_runs_inspected']}` / `{actions['job_runs_inspected']}`",
        f"- Dependabot open alerts: `{security['dependabot_open']}`",
        f"- Code scanning open alerts: `{security['code_scanning_open']}`",
        f"- Secret scanning open alerts: `{security['secret_scanning_open']}`",
        f"- Dependency graph SBOM: `{security['sbom_status']}`",
        "",
        "## Merge settings",
        "",
        f"- Merge commit: `{repo.get('allow_merge_commit')}`",
        f"- Squash merge: `{repo.get('allow_squash_merge')}`",
        f"- Rebase merge: `{repo.get('allow_rebase_merge')}`",
        f"- Auto-merge: `{repo.get('allow_auto_merge')}`",
        f"- Update branch: `{repo.get('allow_update_branch')}`",
        "",
        "## Endpoint verification",
        "",
        "| Endpoint | Status | Count | Error |",
        "|---|---|---:|---|",
    ]
    for record in client.records:
        error = (record.error or "-").replace("\n", " ")[:180]
        lines.append(f"| `{record.name}` | `{record.status}` | {record.count or 0} | {error} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `VERIFIED`: API response was captured.",
            "- `VERIFIED_TRUNCATED`: configured item/page limit was reached.",
            "- `BLOCKED`: authentication or permission prevented access.",
            "- `NOT_AVAILABLE`: feature disabled, unavailable, absent, or returned 404.",
            "- An inaccessible endpoint is never reported as an empty successful result.",
            "",
            "## Evidence",
            "",
            "See `SUMMARY.json`, `tables/`, `raw/`, `ARTIFACT_MANIFEST.json`, and `SHA256SUMS`.",
            "Browser-only and account-level checks are listed in `MANUAL_CHECKS.md`.",
            "",
        ]
    )
    return "\n".join(lines)


def _manual_checks(repo: str) -> str:
    return f"""# Manual GitHub checks

Repository: `{repo}`

These items may require browser, billing, organization, enterprise, or GitHub App access:

- Actions usage, spending limit, billing holds, hosted-runner availability
- Organization or enterprise Actions policy
- Rulesets and classic branch-protection UI agreement
- Required checks, approvals, signed commits, force-push and deletion restrictions
- Environment protection rules and installed GitHub Apps
- GitHub Advanced Security licensing and push-protection settings
- Dependency graph manifest recognition and dependency submission producers

The exporter is read-only. Secret values, variable values, webhook callback URLs,
and deploy-key material are deliberately excluded.

Browser locations:

- https://github.com/{repo}
- https://github.com/{repo}/issues
- https://github.com/{repo}/pulls
- https://github.com/{repo}/actions
- https://github.com/{repo}/security
- https://github.com/{repo}/network/dependencies
- https://github.com/{repo}/settings
"""


def finalize_report(
    *,
    client: GhClient,
    config: Any,
    run_dir: Path,
    core_failures: list[str],
) -> dict[str, Any]:
    tables, _security_rows = _build_tables(client, run_dir, config.duplicate_threshold)
    repository = client.datasets.get("repository") or {}
    issues = tables["issue_rows"]
    prs = tables["pr_rows"]
    runs = tables["run_rows"]
    jobs = tables["job_rows"]
    open_issues = [row for row in issues if row["state"] == "open"]
    open_prs = [row for row in prs if row["state"] == "open"]
    main_status = client.datasets.get("main_combined_status") or {}
    main_checks = client.datasets.get("main_check_runs")

    summary = {
        "schema_version": 1,
        "status": "PARTIALLY_VERIFIED" if core_failures else "VERIFIED",
        "repo": config.repo,
        "finished_at": iso_now(),
        "api_version": config.api_version,
        "deep": config.deep,
        "api_calls": client.api_calls,
        "core_failures": core_failures,
        "repository": {
            "visibility": repository.get("visibility"),
            "private": repository.get("private"),
            "archived": repository.get("archived"),
            "default_branch": repository.get("default_branch"),
            "allow_auto_merge": repository.get("allow_auto_merge"),
            "allow_merge_commit": repository.get("allow_merge_commit"),
            "allow_rebase_merge": repository.get("allow_rebase_merge"),
            "allow_squash_merge": repository.get("allow_squash_merge"),
            "allow_update_branch": repository.get("allow_update_branch"),
            "security_and_analysis": repository.get("security_and_analysis"),
        },
        "head": {
            "sha": client.datasets.get("head_sha"),
            "combined_status": main_status.get("state") if isinstance(main_status, dict) else None,
            "check_run_count": len(main_checks) if isinstance(main_checks, list) else None,
        },
        "issues": {
            "total": len(issues),
            "open": len(open_issues),
            "closed": len(issues) - len(open_issues),
            "possible_duplicate_pairs": len(tables["duplicate_rows"]),
        },
        "pull_requests": {
            "total": len(prs),
            "open": len(open_prs),
            "open_draft": sum(bool(row["draft"]) for row in open_prs),
            "open_ready": sum(not bool(row["draft"]) for row in open_prs),
            "open_stacked": sum(bool(row["stacked_on_non_default"]) for row in open_prs),
            "open_stale_30d": sum(
                isinstance(row["age_since_update_days"], int)
                and row["age_since_update_days"] >= 30
                for row in open_prs
            ),
            "merged": sum(bool(row["merged_at"]) for row in prs),
        },
        "actions": {
            "workflow_count": len(tables["workflow_rows"]),
            "run_count_exported": len(runs),
            "status_counts": dict(Counter(str(row["status"]) for row in runs)),
            "conclusion_counts": dict(Counter(str(row["conclusion"]) for row in runs)),
            "job_runs_inspected": len(jobs),
            "zero_job_runs_inspected": sum(bool(row.get("zero_jobs")) for row in jobs),
        },
        "security": {
            "dependabot_open": _verified_count(client, "dependabot_alerts_open"),
            "code_scanning_open": _verified_count(client, "code_scanning_alerts_open"),
            "secret_scanning_open": _verified_count(client, "secret_scanning_alerts_open"),
            "sbom_status": client.status_for("dependency_graph_sbom") or "NOT_REQUESTED",
        },
        "endpoint_status_counts": dict(Counter(record.status for record in client.records)),
    }
    write_json(run_dir / "SUMMARY.json", summary)
    markdown = _markdown(summary, client)
    (run_dir / "REPORT.md").write_text(markdown + "\n", encoding="utf-8")
    (run_dir / "REPORT.html").write_text(
        "<!doctype html><html lang='ja'><meta charset='utf-8'><title>GitHub Audit</title>"
        "<style>body{font-family:system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem}"
        "pre{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:8px}</style>"
        f"<h1>GitHub Repository Audit</h1><pre>{html.escape(markdown)}</pre></html>",
        encoding="utf-8",
    )
    (run_dir / "MANUAL_CHECKS.md").write_text(_manual_checks(config.repo), encoding="utf-8")
    (run_dir / "status.txt").write_text(summary["status"] + "\n", encoding="utf-8")
    exit_code = 2 if core_failures else 0
    (run_dir / "exit_code.txt").write_text(f"{exit_code}\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "repo": config.repo,
        "status": summary["status"],
        "created_at": iso_now(),
        "generator": "loto-github-audit",
        "python": sys.version,
        "read_only": True,
        "redaction": {
            "secret_values_exported": False,
            "variable_values_exported": False,
            "webhook_callback_urls_exported": False,
            "deploy_key_material_exported": False,
        },
    }
    write_json(run_dir / "ARTIFACT_MANIFEST.json", manifest)
    checksum_lines = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            relative = str(path.relative_to(run_dir)).replace("\\", "/")
            checksum_lines.append(f"{sha256_file(path)}  {relative}")
    (run_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    zip_path = run_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    arcname=str(Path(run_dir.name) / path.relative_to(run_dir)).replace("\\", "/"),
                )
    with zipfile.ZipFile(zip_path) as archive:
        bad_file = archive.testzip()
        if bad_file is not None:
            raise RuntimeError(f"ZIP CRC verification failed at {bad_file}")
    zip_sha = sha256_file(zip_path)
    zip_path.with_suffix(".zip.sha256").write_text(
        f"{zip_sha}  {zip_path.name}\n", encoding="utf-8"
    )
    summary["run_dir"] = str(run_dir)
    summary["zip"] = str(zip_path)
    summary["zip_sha256"] = zip_sha
    summary["exit_code"] = exit_code
    client.log("INFO", "audit_complete", **summary)
    return summary
