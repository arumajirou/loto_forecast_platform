"""CSV and graph builders for GitHub audit reports."""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
from collections.abc import Iterable, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from loto.github_audit.core import GhClient


def _value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else value


def _csv(path: Path, rows: Iterable[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _value(row.get(field)) for field in fields})


def _time(value: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def issue_rows(client: GhClient) -> list[dict[str, Any]]:
    return [
        {
            "number": x.get("number"),
            "state": x.get("state"),
            "state_reason": x.get("state_reason"),
            "title": x.get("title"),
            "author": (x.get("user") or {}).get("login"),
            "assignees": [v.get("login") for v in x.get("assignees", [])],
            "labels": [v.get("name") for v in x.get("labels", [])],
            "comments": x.get("comments"),
            "created_at": x.get("created_at"),
            "updated_at": x.get("updated_at"),
            "closed_at": x.get("closed_at"),
            "html_url": x.get("html_url"),
        }
        for x in client.datasets.get("issues") or []
    ]


def pr_rows(client: GhClient) -> list[dict[str, Any]]:
    default = (client.datasets.get("repository") or {}).get("default_branch")
    now = dt.datetime.now(dt.UTC)
    rows = []
    for x in client.datasets.get("pulls") or []:
        updated = _time(x.get("updated_at"))
        base = (x.get("base") or {}).get("ref")
        rows.append(
            {
                "number": x.get("number"),
                "state": x.get("state"),
                "draft": x.get("draft"),
                "merged_at": x.get("merged_at"),
                "title": x.get("title"),
                "author": (x.get("user") or {}).get("login"),
                "base_ref": base,
                "head_ref": (x.get("head") or {}).get("ref"),
                "head_sha": (x.get("head") or {}).get("sha"),
                "stacked_on_non_default": bool(base and base != default),
                "created_at": x.get("created_at"),
                "updated_at": x.get("updated_at"),
                "age_since_update_days": (now - updated).days if updated else None,
                "html_url": x.get("html_url"),
            }
        )
    return rows


def workflow_rows(client: GhClient) -> list[dict[str, Any]]:
    return [
        {
            key: x.get(key)
            for key in (
                "id",
                "name",
                "path",
                "state",
                "created_at",
                "updated_at",
                "html_url",
            )
        }
        for x in client.datasets.get("workflows") or []
    ]


def run_rows(client: GhClient) -> list[dict[str, Any]]:
    rows = []
    for x in client.datasets.get("workflow_runs") or []:
        created = _time(x.get("created_at"))
        updated = _time(x.get("updated_at"))
        rows.append(
            {
                "id": x.get("id"),
                "run_number": x.get("run_number"),
                "run_attempt": x.get("run_attempt"),
                "name": x.get("name"),
                "event": x.get("event"),
                "status": x.get("status"),
                "conclusion": x.get("conclusion"),
                "head_branch": x.get("head_branch"),
                "head_sha": x.get("head_sha"),
                "created_at": x.get("created_at"),
                "updated_at": x.get("updated_at"),
                "duration_seconds": (
                    round((updated - created).total_seconds(), 3)
                    if created and updated
                    else None
                ),
                "actor": (x.get("actor") or {}).get("login"),
                "html_url": x.get("html_url"),
            }
        )
    return rows


def security_rows(client: GhClient) -> list[dict[str, Any]]:
    rows = []
    for kind, name in (
        ("dependabot", "dependabot_alerts_open"),
        ("code_scanning", "code_scanning_alerts_open"),
        ("secret_scanning", "secret_scanning_alerts_open"),
    ):
        for x in client.datasets.get(name) or []:
            rows.append(
                {
                    "alert_type": kind,
                    "number": x.get("number"),
                    "state": x.get("state"),
                    "severity": (
                        (x.get("security_advisory") or {}).get("severity")
                        or (x.get("rule") or {}).get("security_severity_level")
                        or x.get("secret_type_display_name")
                    ),
                    "created_at": x.get("created_at"),
                    "updated_at": x.get("updated_at"),
                    "html_url": x.get("html_url"),
                }
            )
    return rows


def duplicate_rows(rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    def normal(title: Any) -> str:
        text = re.sub(r"#\d+", "", str(title or "").lower())
        return " ".join(
            re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff]+", " ", text).split()
        )

    opened = [x for x in rows if x.get("state") == "open"]
    result = []
    for index, left in enumerate(opened):
        for right in opened[index + 1 :]:
            score = SequenceMatcher(
                None,
                normal(left.get("title")),
                normal(right.get("title")),
            ).ratio()
            if score >= threshold:
                result.append(
                    {
                        "issue_a": left.get("number"),
                        "issue_b": right.get("number"),
                        "similarity": round(score, 4),
                        "title_a": left.get("title"),
                        "title_b": right.get("title"),
                    }
                )
    return sorted(result, key=lambda x: x["similarity"], reverse=True)


def build_tables(client: GhClient, run_dir: Path, threshold: float) -> dict[str, Any]:
    root = run_dir / "tables"
    issues = issue_rows(client)
    prs = pr_rows(client)
    workflows = workflow_rows(client)
    runs = run_rows(client)
    jobs = client.datasets.get("action_job_rows") or []
    security = security_rows(client)
    duplicates = duplicate_rows(issues, threshold)
    specs = [
        (
            "issues.csv",
            issues,
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
        ),
        (
            "pull_requests.csv",
            prs,
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
        ),
        (
            "workflows.csv",
            workflows,
            ("id", "name", "path", "state", "created_at", "updated_at", "html_url"),
        ),
        (
            "workflow_runs.csv",
            runs,
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
        ),
        (
            "action_run_jobs.csv",
            jobs,
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
        ),
        (
            "security_alerts.csv",
            security,
            (
                "alert_type",
                "number",
                "state",
                "severity",
                "created_at",
                "updated_at",
                "html_url",
            ),
        ),
        (
            "endpoint_status.csv",
            [x.to_dict() for x in client.records],
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
        ),
        (
            "possible_duplicate_issues.csv",
            duplicates,
            ("issue_a", "issue_b", "similarity", "title_a", "title_b"),
        ),
    ]
    for name, rows, fields in specs:
        _csv(root / name, rows, fields)
    branches = [
        {
            "name": x.get("name"),
            "protected": x.get("protected"),
            "sha": (x.get("commit") or {}).get("sha"),
        }
        for x in client.datasets.get("branches") or []
    ]
    _csv(root / "branches.csv", branches, ("name", "protected", "sha"))
    default = str(
        (client.datasets.get("repository") or {}).get("default_branch") or "main"
    )
    _write_stack(root / "pr_stack.dot", prs, default)
    return {
        "issues": issues,
        "prs": prs,
        "workflows": workflows,
        "runs": runs,
        "jobs": jobs,
        "duplicates": duplicates,
    }


def _write_stack(path: Path, rows: list[dict[str, Any]], default: str) -> None:
    heads = {
        str(x["head_ref"]): x["number"]
        for x in rows
        if x.get("state") == "open" and x.get("head_ref")
    }
    lines = [
        "digraph pull_request_stack {",
        '  rankdir="LR";',
        '  node [shape=box, fontname="Arial"];',
        f'  "{default}" [shape=oval];',
    ]
    for row in rows:
        if row.get("state") != "open":
            continue
        number = row.get("number")
        base = str(row.get("base_ref") or default)
        title = str(row.get("title") or "").replace('"', r'\"')[:80]
        state = "Draft" if row.get("draft") else "Ready"
        parent = f"PR#{heads[base]}" if base in heads else base
        lines.extend(
            [
                f'  "PR#{number}" [label="PR #{number}\\n{state}\\n{title}"];',
                f'  "{parent}" -> "PR#{number}";',
            ]
        )
    path.write_text("\n".join([*lines, "}"]) + "\n", encoding="utf-8")
