#!/usr/bin/env python3
"""Build a lightweight GitHub repository observability summary.

The script intentionally uses only the Python standard library. It reports GitHub
control-plane state; it does not evaluate model accuracy or scientific gates.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _api_get(api_base: str, token: str | None, path: str) -> Any:
    request = Request(
        f"{api_base.rstrip('/')}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed GitHub API base
            return json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {path} failed: HTTP {exc.code}: {body[:1000]}") from exc


def _md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _issue_labels(issue: dict[str, Any]) -> list[str]:
    return sorted(
        str(label.get("name", ""))
        for label in issue.get("labels", [])
        if isinstance(label, dict) and label.get("name")
    )


def _build_markdown(payload: dict[str, Any]) -> str:
    repo = payload["repository"]
    server = payload["server_url"]
    project_url = payload["project_url"]
    lines = [
        "# Repository observability dashboard",
        "",
        (
            "> Navigation/status only. Runtime certification and scientific results "
            "require their own immutable evidence."
        ),
        "",
        "## Current GitHub state",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Repository | [{repo}]({server}/{repo}) |",
        (
            f"| Main SHA | [`{payload['main_sha'][:12]}`]"
            f"({server}/{repo}/commit/{payload['main_sha']}) |"
        ),
        f"| Open issues | {payload['open_issue_count']} |",
        f"| Open pull requests | {payload['open_pr_count']} |",
        f"| Active workflows | {payload['active_workflow_count']} |",
        f"| Repository Project | [Runtime & Model Certification]({project_url}) |",
        "",
        "## Quick navigation",
        "",
        f"- [Project]({project_url})",
        f"- [Open issues]({server}/{repo}/issues?q=is%3Aissue+state%3Aopen)",
        f"- [Pull requests]({server}/{repo}/pulls)",
        f"- [Actions]({server}/{repo}/actions)",
        f"- [Insights]({server}/{repo}/pulse)",
        f"- [Operations reference]({server}/{repo}/blob/main/docs/GITHUB_OPERATIONS_DASHBOARD.md)",
        "",
        "## Open issues",
        "",
        "| Issue | Labels | Assignees | Updated |",
        "|---|---|---|---|",
    ]

    for issue in payload["open_issues"]:
        labels = ", ".join(issue["labels"]) or "—"
        assignees = ", ".join(issue["assignees"]) or "—"
        lines.append(
            f"| [#{issue['number']} {_md(issue['title'])}]({issue['html_url']}) "
            f"| {_md(labels)} | {_md(assignees)} | `{_md(issue['updated_at'])}` |"
        )

    lines.extend(
        [
            "",
            "## Active workflow inventory",
            "",
            (
                "The repository currently has many specialized workflows. Use `ci` as the "
                "canonical repository gate and this dashboard as the navigation surface. "
                "Provider/repair workflows remain evidence-specific until separately consolidated."
            ),
            "",
            "| Workflow | Path |",
            "|---|---|",
        ]
    )
    for workflow in payload["active_workflows"]:
        lines.append(
            f"| [{_md(workflow['name'])}]({workflow['html_url']}) | `{_md(workflow['path'])}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation boundaries",
            "",
            "- An open/closed Issue is operational state, not model quality evidence.",
            (
                "- An active workflow is an execution surface, not proof that the model/runtime "
                "is certified."
            ),
            (
                "- Project fields are a dashboard cache; immutable run artifacts and SHA-256 "
                "manifests remain authoritative."
            ),
            (
                "- Holdout, Prospective, champion, and promotion state must be read from their "
                "explicit scientific/governance evidence; this script never infers them."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def build_payload() -> dict[str, Any]:
    repository = os.environ.get("GITHUB_REPOSITORY", "arumajirou/loto_forecast_platform")
    token = os.environ.get("GITHUB_TOKEN")
    api_base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    project_url = os.environ.get(
        "LOTO_PROJECT_URL", "https://github.com/users/arumajirou/projects/1"
    )

    ref = _api_get(api_base, token, f"/repos/{repository}/git/ref/heads/main")
    issues_and_prs = _api_get(
        api_base, token, f"/repos/{repository}/issues?state=open&per_page=100"
    )
    workflows_payload = _api_get(
        api_base, token, f"/repos/{repository}/actions/workflows?per_page=100"
    )

    issues = [item for item in issues_and_prs if "pull_request" not in item]
    prs = [item for item in issues_and_prs if "pull_request" in item]
    workflows = [
        workflow
        for workflow in workflows_payload.get("workflows", [])
        if workflow.get("state") == "active"
    ]

    normalized_issues = []
    for issue in issues:
        normalized_issues.append(
            {
                "number": int(issue["number"]),
                "title": str(issue["title"]),
                "html_url": str(issue["html_url"]),
                "labels": _issue_labels(issue),
                "assignees": sorted(
                    str(user.get("login", ""))
                    for user in issue.get("assignees", [])
                    if isinstance(user, dict) and user.get("login")
                ),
                "updated_at": str(issue.get("updated_at", "")),
            }
        )

    normalized_issues.sort(key=lambda item: item["number"], reverse=True)
    normalized_workflows = sorted(
        (
            {
                "name": str(workflow.get("name") or workflow.get("path") or "unnamed"),
                "path": str(workflow.get("path", "")),
                "html_url": str(workflow.get("html_url", "")),
            }
            for workflow in workflows
        ),
        key=lambda item: (item["name"].lower(), item["path"]),
    )

    return {
        "schema_version": 1,
        "repository": repository,
        "server_url": server_url,
        "project_url": project_url,
        "main_sha": str(ref["object"]["sha"]),
        "open_issue_count": len(normalized_issues),
        "open_pr_count": len(prs),
        "active_workflow_count": len(normalized_workflows),
        "open_issues": normalized_issues,
        "active_workflows": normalized_workflows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args()

    payload = build_payload()
    markdown = _build_markdown(payload)

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown + "\n", encoding="utf-8")
    else:
        print(markdown)

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
