"""Repository audit orchestration."""

from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loto.github_audit.core import (
    DEFAULT_API_VERSION,
    GhClient,
    classify_error,
    iso_now,
    redact,
    redact_variable_values,
    safe_slug,
    write_json,
)
from loto.github_audit.reporting import finalize_report


@dataclass(frozen=True, slots=True)
class AuditConfig:
    repo: str
    output_root: Path
    api_version: str = DEFAULT_API_VERSION
    deep: bool = False
    max_items: int = 5000
    max_pages: int = 100
    max_action_runs: int = 500
    max_run_jobs: int = 100
    max_pr_details: int = 200
    max_issue_details: int = 500
    timeout: int = 120
    duplicate_threshold: float = 0.90


def _safe_hooks(value: Any) -> Any:
    if not isinstance(value, list):
        return redact(value)
    result = []
    for hook in value:
        if not isinstance(hook, dict):
            continue
        result.append(
            {
                "id": hook.get("id"),
                "type": hook.get("type"),
                "name": hook.get("name"),
                "active": hook.get("active"),
                "events": hook.get("events"),
                "created_at": hook.get("created_at"),
                "updated_at": hook.get("updated_at"),
                "config": {
                    "content_type": (hook.get("config") or {}).get("content_type"),
                    "insecure_ssl": (hook.get("config") or {}).get("insecure_ssl"),
                    "url": "<REDACTED>",
                },
            }
        )
    return result


def _safe_deploy_keys(value: Any) -> Any:
    if not isinstance(value, list):
        return redact(value)
    return [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "verified": item.get("verified"),
            "read_only": item.get("read_only"),
            "created_at": item.get("created_at"),
            "added_by": item.get("added_by"),
            "key": "<REDACTED>",
        }
        for item in value
        if isinstance(item, dict)
    ]


class AuditRunner:
    def __init__(self, config: AuditConfig) -> None:
        if config.repo.count("/") != 1:
            raise ValueError("repo must use OWNER/REPO form")
        self.config = config
        self.owner, self.repo_name = config.repo.split("/", 1)
        timestamp = iso_now().replace("-", "").replace(":", "").replace("+00:00", "Z")
        self.run_dir = (
            config.output_root.expanduser().resolve()
            / f"{safe_slug(config.repo)}-audit-{timestamp}"
        )
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.client = GhClient(
            repo=config.repo,
            run_dir=self.run_dir,
            api_version=config.api_version,
            timeout=config.timeout,
            max_pages=config.max_pages,
            max_items=config.max_items,
        )
        self.core_failures: list[str] = []

    def _core(self, name: str, value: Any) -> Any:
        if value is None:
            self.core_failures.append(name)
        return value

    def collect(self) -> dict[str, Any]:
        self.client.log("INFO", "audit_start", repo=self.config.repo, deep=self.config.deep)
        self.client.verify_prerequisites()

        repository = self._core(
            "repository",
            self.client.get("repository", f"repos/{self.config.repo}"),
        )
        if not isinstance(repository, dict):
            summary = finalize_report(
                client=self.client,
                config=self.config,
                run_dir=self.run_dir,
                core_failures=self.core_failures,
            )
            return summary

        default_branch = str(repository.get("default_branch") or "main")
        self.client.datasets["default_branch"] = default_branch
        branch_ref = urllib.parse.quote(default_branch, safe="")
        head = self.client.get(
            "default_branch_head",
            f"repos/{self.config.repo}/commits/{branch_ref}",
        )
        if isinstance(head, dict) and head.get("sha"):
            head_sha = str(head["sha"])
            self.client.datasets["head_sha"] = head_sha
            self.client.get(
                "main_combined_status",
                f"repos/{self.config.repo}/commits/{head_sha}/status",
            )
            self.client.get_list(
                "main_check_runs",
                f"repos/{self.config.repo}/commits/{head_sha}/check-runs",
                item_key="check_runs",
                max_items=1000,
            )
            self.client.get_list(
                "main_workflow_runs",
                f"repos/{self.config.repo}/actions/runs",
                params={"head_sha": head_sha},
                item_key="workflow_runs",
                max_items=1000,
            )

        issues_all = self._core(
            "issues_all",
            self.client.get_list(
                "issues_all",
                f"repos/{self.config.repo}/issues",
                params={"state": "all", "sort": "updated", "direction": "desc"},
            ),
        )
        if isinstance(issues_all, list):
            issues = [item for item in issues_all if not item.get("pull_request")]
            self.client.datasets["issues"] = issues
            write_json(
                self.run_dir / "raw" / "issues_only.json",
                {"_audit": {"status": "DERIVED", "fetched_at": iso_now()}, "data": issues},
            )

        pulls = self._core(
            "pulls_all",
            self.client.get_list(
                "pulls_all",
                f"repos/{self.config.repo}/pulls",
                params={"state": "all", "sort": "updated", "direction": "desc"},
            ),
        )
        if isinstance(pulls, list):
            self.client.datasets["pulls"] = pulls

        self._collect_repository_inventory(default_branch)
        self._collect_actions()
        self._collect_security_and_settings(branch_ref)

        if self.config.deep:
            self._collect_deep_issues()
            self._collect_deep_prs()
            self._collect_action_jobs()

        return finalize_report(
            client=self.client,
            config=self.config,
            run_dir=self.run_dir,
            core_failures=self.core_failures,
        )

    def _collect_repository_inventory(self, default_branch: str) -> None:
        repo = self.config.repo
        self.client.get_list("branches", f"repos/{repo}/branches")
        self.client.get_list(
            "commits_recent",
            f"repos/{repo}/commits",
            params={"sha": default_branch},
            max_items=min(self.config.max_items, 500),
        )
        self.client.get_list("tags", f"repos/{repo}/tags", max_items=1000)
        self.client.get_list("releases", f"repos/{repo}/releases", max_items=1000)
        self.client.get_list(
            "contributors",
            f"repos/{repo}/contributors",
            params={"anon": True},
            max_items=1000,
        )
        self.client.get_list(
            "forks",
            f"repos/{repo}/forks",
            params={"sort": "newest"},
            max_items=1000,
        )

    def _collect_actions(self) -> None:
        repo = self.config.repo
        workflows = self.client.get_list(
            "workflows",
            f"repos/{repo}/actions/workflows",
            item_key="workflows",
            max_items=1000,
        )
        self._core("workflows", workflows)
        runs = self.client.get_list(
            "workflow_runs",
            f"repos/{repo}/actions/runs",
            item_key="workflow_runs",
            max_items=self.config.max_action_runs,
        )
        self._core("workflow_runs", runs)
        self.client.get("actions_permissions", f"repos/{repo}/actions/permissions")
        self.client.get(
            "actions_workflow_permissions",
            f"repos/{repo}/actions/permissions/workflow",
        )
        self.client.get(
            "actions_selected_actions",
            f"repos/{repo}/actions/permissions/selected-actions",
        )
        self.client.get_list(
            "actions_runners",
            f"repos/{repo}/actions/runners",
            item_key="runners",
            max_items=1000,
        )
        self.client.get_list(
            "actions_caches",
            f"repos/{repo}/actions/caches",
            item_key="actions_caches",
            max_items=1000,
        )
        self.client.get_list(
            "actions_artifacts",
            f"repos/{repo}/actions/artifacts",
            item_key="artifacts",
        )

    def _collect_security_and_settings(self, branch_ref: str) -> None:
        repo = self.config.repo
        self.client.get_list(
            "dependabot_alerts_open",
            f"repos/{repo}/dependabot/alerts",
            params={"state": "open", "sort": "updated", "direction": "desc"},
        )
        self.client.get_list(
            "code_scanning_alerts_open",
            f"repos/{repo}/code-scanning/alerts",
            params={"state": "open", "sort": "updated", "direction": "desc"},
        )
        self.client.get(
            "code_scanning_default_setup",
            f"repos/{repo}/code-scanning/default-setup",
        )
        self.client.get_list(
            "secret_scanning_alerts_open",
            f"repos/{repo}/secret-scanning/alerts",
            params={"state": "open", "sort": "updated", "direction": "desc"},
        )
        self.client.get_list(
            "repository_security_advisories",
            f"repos/{repo}/security-advisories",
            params={"state": "open"},
        )
        self.client.get(
            "private_vulnerability_reporting",
            f"repos/{repo}/private-vulnerability-reporting",
        )
        self.client.get("dependency_graph_sbom", f"repos/{repo}/dependency-graph/sbom")
        self.client.get(
            "dependabot_config_yml",
            f"repos/{repo}/contents/.github/dependabot.yml",
        )
        self.client.get(
            "dependabot_config_yaml",
            f"repos/{repo}/contents/.github/dependabot.yaml",
        )
        self.client.get_list(
            "repository_rulesets",
            f"repos/{repo}/rulesets",
            params={"includes_parents": True},
            max_items=1000,
        )
        self.client.get_list(
            "active_rules_default_branch",
            f"repos/{repo}/rules/branches/{branch_ref}",
            max_items=1000,
        )
        self.client.get(
            "default_branch_protection",
            f"repos/{repo}/branches/{branch_ref}/protection",
        )
        self.client.get_list(
            "environments",
            f"repos/{repo}/environments",
            item_key="environments",
            max_items=1000,
        )
        self.client.get_list(
            "collaborators",
            f"repos/{repo}/collaborators",
            params={"affiliation": "all"},
        )
        hooks = self.client.get_list("webhooks_metadata", f"repos/{repo}/hooks", max_items=1000)
        if hooks is not None:
            safe = _safe_hooks(hooks)
            self.client.datasets["webhooks_metadata"] = safe
            write_json(
                self.run_dir / "raw" / "webhooks_metadata.json",
                {"_audit": {"status": "VERIFIED_REDACTED", "fetched_at": iso_now()}, "data": safe},
            )
        keys = self.client.get_list("deploy_keys_metadata", f"repos/{repo}/keys", max_items=1000)
        if keys is not None:
            safe = _safe_deploy_keys(keys)
            self.client.datasets["deploy_keys_metadata"] = safe
            write_json(
                self.run_dir / "raw" / "deploy_keys_metadata.json",
                {"_audit": {"status": "VERIFIED_REDACTED", "fetched_at": iso_now()}, "data": safe},
            )
        self.client.get_list(
            "actions_secrets_metadata",
            f"repos/{repo}/actions/secrets",
            item_key="secrets",
            max_items=1000,
        )
        self.client.get(
            "actions_variables_metadata",
            f"repos/{repo}/actions/variables",
            postprocess=redact_variable_values,
        )

    def _collect_deep_issues(self) -> None:
        issues = self.client.datasets.get("issues")
        if not isinstance(issues, list):
            return
        repo = self.config.repo
        open_issues = [item for item in issues if item.get("state") == "open"]
        for item in open_issues[: self.config.max_issue_details]:
            number = int(item["number"])
            folder = self.run_dir / "raw" / "issue_details" / f"issue_{number:04d}"
            self.client.get(
                f"issue_{number}_detail",
                f"repos/{repo}/issues/{number}",
                raw_path=folder / "detail.json",
            )
            self.client.get_list(
                f"issue_{number}_comments",
                f"repos/{repo}/issues/{number}/comments",
                raw_path=folder / "comments.json",
            )
            self.client.get_list(
                f"issue_{number}_events",
                f"repos/{repo}/issues/{number}/events",
                raw_path=folder / "events.json",
            )

    def _collect_deep_prs(self) -> None:
        pulls = self.client.datasets.get("pulls")
        if not isinstance(pulls, list):
            return
        repo = self.config.repo
        open_pulls = [item for item in pulls if item.get("state") == "open"]
        for item in open_pulls[: self.config.max_pr_details]:
            number = int(item["number"])
            folder = self.run_dir / "raw" / "pr_details" / f"pr_{number:04d}"
            detail = self.client.get(
                f"pr_{number}_detail",
                f"repos/{repo}/pulls/{number}",
                raw_path=folder / "detail.json",
            )
            self.client.get_list(
                f"pr_{number}_reviews",
                f"repos/{repo}/pulls/{number}/reviews",
                raw_path=folder / "reviews.json",
            )
            self.client.get_list(
                f"pr_{number}_review_comments",
                f"repos/{repo}/pulls/{number}/comments",
                raw_path=folder / "review_comments.json",
            )
            self.client.get_list(
                f"pr_{number}_conversation_comments",
                f"repos/{repo}/issues/{number}/comments",
                raw_path=folder / "conversation_comments.json",
            )
            self.client.get_list(
                f"pr_{number}_files",
                f"repos/{repo}/pulls/{number}/files",
                raw_path=folder / "files.json",
            )
            self._collect_review_threads(number, folder / "review_threads.json")
            head_sha = None
            if isinstance(detail, dict):
                head_sha = (detail.get("head") or {}).get("sha")
            if not head_sha:
                head_sha = (item.get("head") or {}).get("sha")
            if head_sha:
                self.client.get(
                    f"pr_{number}_combined_status",
                    f"repos/{repo}/commits/{head_sha}/status",
                    raw_path=folder / "combined_status.json",
                )
                self.client.get_list(
                    f"pr_{number}_check_runs",
                    f"repos/{repo}/commits/{head_sha}/check-runs",
                    item_key="check_runs",
                    max_items=1000,
                    raw_path=folder / "check_runs.json",
                )
                self.client.get_list(
                    f"pr_{number}_workflow_runs",
                    f"repos/{repo}/actions/runs",
                    params={"head_sha": head_sha},
                    item_key="workflow_runs",
                    max_items=1000,
                    raw_path=folder / "workflow_runs.json",
                )

    def _collect_review_threads(self, number: int, raw_path: Path) -> None:
        query = """
query($owner:String!, $name:String!, $number:Int!, $endCursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$endCursor) {
        nodes {
          id isResolved isOutdated path line originalLine
          comments(first:100) {
            nodes { id body createdAt updatedAt url path line originalLine author { login } }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""
        command = [
            "gh",
            "api",
            "graphql",
            "--paginate",
            "--slurp",
            "-f",
            f"query={query}",
            "-F",
            f"owner={self.owner}",
            "-F",
            f"name={self.repo_name}",
            "-F",
            f"number={number}",
        ]
        started = time.monotonic()
        self.client.api_calls += 1
        completed = self.client.run_command(command)
        duration_ms = round((time.monotonic() - started) * 1000)
        status = "VERIFIED"
        error = None
        threads: list[Any] = []
        if completed.returncode == 0:
            try:
                pages = json.loads(completed.stdout) if completed.stdout.strip() else []
                for page in pages if isinstance(pages, list) else [pages]:
                    connection = (
                        (page.get("data") or {})
                        .get("repository", {})
                        .get("pullRequest", {})
                        .get("reviewThreads", {})
                    )
                    nodes = connection.get("nodes", [])
                    if isinstance(nodes, list):
                        threads.extend(nodes)
                threads = redact(threads)
            except (json.JSONDecodeError, AttributeError) as exc:
                status = "FAILED"
                error = f"Invalid GraphQL response: {exc}"
        else:
            status = classify_error(completed.stderr, completed.returncode)
            error = completed.stderr.strip()[-4000:]
        ok = status == "VERIFIED"
        write_json(
            raw_path,
            {
                "_audit": {
                    "name": f"pr_{number}_review_threads",
                    "endpoint": "graphql PullRequest.reviewThreads",
                    "status": status,
                    "fetched_at": iso_now(),
                    "duration_ms": duration_ms,
                    "returncode": completed.returncode,
                    "error": error,
                },
                "data": threads if ok else None,
            },
        )
        self.client._record(
            name=f"pr_{number}_review_threads",
            endpoint="graphql PullRequest.reviewThreads",
            status=status,
            ok=ok,
            count=len(threads) if ok else None,
            duration_ms=duration_ms,
            returncode=completed.returncode,
            error=error,
            raw_path=raw_path,
        )

    def _collect_action_jobs(self) -> None:
        runs = self.client.datasets.get("workflow_runs")
        if not isinstance(runs, list):
            return
        rows: list[dict[str, Any]] = []
        for run in runs[: self.config.max_run_jobs]:
            run_id = run.get("id")
            if not run_id:
                continue
            jobs = self.client.get_list(
                f"run_{run_id}_jobs",
                f"repos/{self.config.repo}/actions/runs/{run_id}/jobs",
                item_key="jobs",
                max_items=1000,
                raw_path=self.run_dir / "raw" / "action_jobs" / f"run_{run_id}.json",
            )
            rows.append(
                {
                    "run_id": run_id,
                    "run_number": run.get("run_number"),
                    "name": run.get("name"),
                    "event": run.get("event"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "created_at": run.get("created_at"),
                    "updated_at": run.get("updated_at"),
                    "jobs_status": "VERIFIED" if isinstance(jobs, list) else "UNKNOWN",
                    "job_count": len(jobs) if isinstance(jobs, list) else None,
                    "zero_jobs": isinstance(jobs, list) and not jobs,
                    "html_url": run.get("html_url"),
                }
            )
        self.client.datasets["action_job_rows"] = rows
