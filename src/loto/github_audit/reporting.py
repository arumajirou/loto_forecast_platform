"""Human- and machine-readable GitHub repository audit reports."""

from __future__ import annotations

import html
from collections import Counter
from pathlib import Path
from typing import Any

from loto.github_audit.artifacts import package
from loto.github_audit.core import GhClient, iso_now, write_json
from loto.github_audit.tables import build_tables


def _count(client: GhClient, name: str) -> int | str:
    data = client.datasets.get(name)
    if isinstance(data, list):
        return len(data)
    return f"UNKNOWN:{client.status_for(name) or 'NOT_REQUESTED'}"


def _summary(
    client: GhClient,
    config: Any,
    run_dir: Path,
    core_failures: list[str],
    tables: dict[str, Any],
) -> dict[str, Any]:
    gaps = [x.name for x in client.records if not x.ok]
    if core_failures:
        status, exit_code = "PARTIALLY_VERIFIED", 2
    elif gaps:
        status, exit_code = "VERIFIED_WITH_GAPS", 0
    else:
        status, exit_code = "VERIFIED", 0
    repo = client.datasets.get("repository") or {}
    issues = tables["issues"]
    prs = tables["prs"]
    runs = tables["runs"]
    jobs = tables["jobs"]
    open_issues = [x for x in issues if x.get("state") == "open"]
    open_prs = [x for x in prs if x.get("state") == "open"]
    status_data = client.datasets.get("main_combined_status") or {}
    checks = client.datasets.get("main_check_runs")
    return {
        "schema_version": 1,
        "status": status,
        "repo": config.repo,
        "finished_at": iso_now(),
        "api_version": config.api_version,
        "deep": config.deep,
        "api_calls": client.api_calls,
        "core_failures": core_failures,
        "non_core_gaps": [x for x in gaps if x not in core_failures],
        "run_dir": str(run_dir),
        "zip": str(run_dir.with_suffix(".zip")),
        "exit_code": exit_code,
        "repository": {
            key: repo.get(key)
            for key in (
                "visibility",
                "private",
                "archived",
                "default_branch",
                "allow_auto_merge",
                "allow_merge_commit",
                "allow_rebase_merge",
                "allow_squash_merge",
                "allow_update_branch",
                "security_and_analysis",
            )
        },
        "head": {
            "sha": client.datasets.get("head_sha"),
            "combined_status": (
                status_data.get("state") if isinstance(status_data, dict) else None
            ),
            "check_run_count": len(checks) if isinstance(checks, list) else None,
        },
        "issues": {
            "total": len(issues),
            "open": len(open_issues),
            "closed": len(issues) - len(open_issues),
            "possible_duplicate_pairs": len(tables["duplicates"]),
        },
        "pull_requests": {
            "total": len(prs),
            "open": len(open_prs),
            "open_draft": sum(bool(x.get("draft")) for x in open_prs),
            "open_ready": sum(not bool(x.get("draft")) for x in open_prs),
            "open_stacked": sum(bool(x.get("stacked_on_non_default")) for x in open_prs),
            "open_stale_30d": sum(
                isinstance(x.get("age_since_update_days"), int) and x["age_since_update_days"] >= 30
                for x in open_prs
            ),
            "merged": sum(bool(x.get("merged_at")) for x in prs),
        },
        "actions": {
            "workflow_count": len(tables["workflows"]),
            "run_count_exported": len(runs),
            "status_counts": dict(Counter(str(x.get("status")) for x in runs)),
            "conclusion_counts": dict(Counter(str(x.get("conclusion")) for x in runs)),
            "job_runs_inspected": len(jobs),
            "zero_job_runs_inspected": sum(bool(x.get("zero_jobs")) for x in jobs),
        },
        "security": {
            "dependabot_open": _count(client, "dependabot_alerts_open"),
            "code_scanning_open": _count(client, "code_scanning_alerts_open"),
            "secret_scanning_open": _count(client, "secret_scanning_alerts_open"),
            "sbom_status": client.status_for("dependency_graph_sbom") or "NOT_REQUESTED",
        },
        "endpoint_status_counts": dict(Counter(x.status for x in client.records)),
    }


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
        f"- Zero-job runs inspected: "
        f"`{actions['zero_job_runs_inspected']}` / "
        f"`{actions['job_runs_inspected']}`",
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
        count = str(record.count) if record.count is not None else "UNKNOWN"
        error = (record.error or "-").replace("\n", " ")[:180]
        lines.append(f"| `{record.name}` | `{record.status}` | {count} | {error} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `VERIFIED`: all requested endpoints were captured.",
            "- `VERIFIED_WITH_GAPS`: non-core endpoints were unavailable.",
            "- `PARTIALLY_VERIFIED`: at least one core endpoint was unavailable.",
            "- Inaccessible endpoints are never reported as empty successful results.",
            "",
            "## Evidence",
            "",
            "See `SUMMARY.json`, `tables/`, `raw/`, `ARTIFACT_MANIFEST.json`, and `SHA256SUMS`.",
            "",
        ]
    )
    return "\n".join(lines)


def _manual(repo: str) -> str:
    return f"""# Manual GitHub checks

Repository: `{repo}`

Review Actions billing and organization policy, rulesets and required checks,
environment protection, installed GitHub Apps, Advanced Security licensing,
push protection, and dependency graph recognition in the browser.

The exporter is read-only. Secret values, variable values, webhook callback URLs,
and deploy-key material are deliberately excluded.
"""


def finalize_report(
    *,
    client: GhClient,
    config: Any,
    run_dir: Path,
    core_failures: list[str],
) -> dict[str, Any]:
    tables = build_tables(client, run_dir, config.duplicate_threshold)
    summary = _summary(client, config, run_dir, core_failures, tables)
    write_json(run_dir / "SUMMARY.json", summary)
    markdown = _markdown(summary, client)
    (run_dir / "REPORT.md").write_text(markdown + "\n", encoding="utf-8")
    (run_dir / "REPORT.html").write_text(
        "<!doctype html><html lang='ja'><meta charset='utf-8'>"
        f"<title>GitHub Audit</title><pre>{html.escape(markdown)}</pre></html>",
        encoding="utf-8",
    )
    (run_dir / "MANUAL_CHECKS.md").write_text(
        _manual(config.repo),
        encoding="utf-8",
    )
    (run_dir / "status.txt").write_text(summary["status"] + "\n", encoding="utf-8")
    (run_dir / "exit_code.txt").write_text(
        f"{summary['exit_code']}\n",
        encoding="utf-8",
    )
    result = {**summary, "zip_sha256": package(run_dir, summary)}
    client.log("INFO", "audit_complete", **result)
    return result
