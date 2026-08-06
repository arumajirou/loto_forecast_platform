"""Core helpers for the read-only GitHub audit exporter."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_API_VERSION = "2026-03-10"
BLOCKED_PATTERNS = (
    "http 401",
    "http 403",
    "requires authentication",
    "resource not accessible",
    "must have admin rights",
    "forbidden",
    "insufficient",
)
NOT_AVAILABLE_PATTERNS = (
    "http 404",
    "not found",
    "advanced security must be enabled",
    "dependency graph is disabled",
    "secret scanning is disabled",
    "code scanning is not enabled",
)
RATE_LIMIT_PATTERNS = ("http 429", "api rate limit exceeded", "secondary rate limit")
SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "client_secret",
    "private_key",
    "pem",
    "encrypted_value",
    "key",
}


def iso_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "audit"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_error(stderr: str, returncode: int) -> str:
    lower = stderr.lower()
    if any(pattern in lower for pattern in RATE_LIMIT_PATTERNS):
        return "RATE_LIMITED"
    if any(pattern in lower for pattern in BLOCKED_PATTERNS):
        return "BLOCKED"
    if any(pattern in lower for pattern in NOT_AVAILABLE_PATTERNS):
        return "NOT_AVAILABLE"
    if returncode == 124:
        return "TIMEOUT"
    if "http 422" in lower:
        return "INVALID_REQUEST"
    return "FAILED"


def redact(value: Any, parent_key: str | None = None) -> Any:
    if parent_key and parent_key.lower() in SENSITIVE_KEYS:
        return "<REDACTED>"
    if isinstance(value, dict):
        return {str(key): redact(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, parent_key) for item in value]
    return value


def redact_variable_values(value: Any) -> Any:
    if not isinstance(value, dict):
        return redact(value)
    variables = value.get("variables", [])
    safe_variables = []
    for item in variables if isinstance(variables, list) else []:
        if isinstance(item, dict):
            safe_variables.append(
                {
                    "name": item.get("name"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "value": "<REDACTED>",
                }
            )
    return {
        "total_count": value.get("total_count", len(safe_variables)),
        "variables": safe_variables,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


@dataclass(slots=True)
class EndpointRecord:
    name: str
    endpoint: str
    status: str
    ok: bool
    count: int | None
    duration_ms: int
    fetched_at: str
    returncode: int
    error: str | None
    raw_file: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GhClient:
    """Authenticated GET-only wrapper around ``gh api``."""

    def __init__(
        self,
        *,
        repo: str,
        run_dir: Path,
        api_version: str = DEFAULT_API_VERSION,
        timeout: int = 120,
        max_pages: int = 100,
        max_items: int = 5000,
    ) -> None:
        self.repo = repo
        self.run_dir = run_dir
        self.raw_dir = run_dir / "raw"
        self.log_path = run_dir / "logs" / "audit.jsonl"
        self.api_version = api_version
        self.timeout = timeout
        self.max_pages = max_pages
        self.max_items = max_items
        self.records: list[EndpointRecord] = []
        self.datasets: dict[str, Any] = {}
        self.api_calls = 0
        self.env = os.environ.copy()
        self.env.update(
            {"GH_REPO": repo, "GH_PAGER": "cat", "PAGER": "cat", "NO_COLOR": "1"}
        )
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, level: str, event: str, **fields: Any) -> None:
        payload = {"ts": iso_now(), "level": level, "event": event, **redact(fields)}
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def run_command(
        self,
        command: list[str],
        *,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.log("DEBUG", "command_start", argv=command)
        try:
            completed = subprocess.run(
                command,
                env=self.env,
                text=True,
                capture_output=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            completed = subprocess.CompletedProcess(
                command,
                127,
                stdout="",
                stderr=f"COMMAND_NOT_FOUND: {exc}",
            )
        except subprocess.TimeoutExpired as exc:
            completed = subprocess.CompletedProcess(
                command,
                124,
                stdout=exc.stdout or "",
                stderr=f"TIMEOUT after {timeout or self.timeout}s: {exc}",
            )
        self.log(
            "DEBUG",
            "command_end",
            argv=command,
            returncode=completed.returncode,
            stderr=completed.stderr[-2000:],
        )
        return completed

    def verify_prerequisites(self) -> None:
        version = self.run_command(["gh", "--version"], timeout=30)
        auth = self.run_command(
            ["gh", "auth", "status", "--hostname", "github.com"],
            timeout=60,
        )
        (self.run_dir / "logs" / "gh-version.txt").write_text(
            version.stdout + version.stderr,
            encoding="utf-8",
        )
        (self.run_dir / "logs" / "gh-auth-status.txt").write_text(
            auth.stdout + auth.stderr,
            encoding="utf-8",
        )
        if version.returncode != 0:
            raise RuntimeError("GitHub CLI `gh` was not found in PATH")
        if auth.returncode != 0:
            raise RuntimeError(
                "gh authentication is unavailable; run "
                "`gh auth login --hostname github.com`"
            )

    def _command(self, endpoint: str, params: dict[str, Any] | None = None) -> list[str]:
        command = [
            "gh",
            "api",
            "--method",
            "GET",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            f"X-GitHub-Api-Version: {self.api_version}",
            endpoint,
        ]
        for key, value in (params or {}).items():
            if value is None:
                continue
            if isinstance(value, bool):
                value = str(value).lower()
            command.extend(["-f", f"{key}={value}"])
        return command

    def _record(
        self,
        *,
        name: str,
        endpoint: str,
        status: str,
        ok: bool,
        count: int | None,
        duration_ms: int,
        returncode: int,
        error: str | None,
        raw_path: Path,
    ) -> None:
        record = EndpointRecord(
            name=name,
            endpoint=endpoint,
            status=status,
            ok=ok,
            count=count,
            duration_ms=duration_ms,
            fetched_at=iso_now(),
            returncode=returncode,
            error=error,
            raw_file=str(raw_path.relative_to(self.run_dir)).replace("\\", "/"),
        )
        self.records.append(record)
        self.log("INFO" if ok else "WARNING", "endpoint_complete", **record.to_dict())

    def get(
        self,
        name: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        postprocess: Callable[[Any], Any] | None = None,
        raw_path: Path | None = None,
    ) -> Any | None:
        started = time.monotonic()
        self.api_calls += 1
        completed = self.run_command(self._command(endpoint, params))
        duration_ms = round((time.monotonic() - started) * 1000)
        status = "VERIFIED"
        error: str | None = None
        data: Any | None = None
        if completed.returncode == 0:
            try:
                data = json.loads(completed.stdout) if completed.stdout.strip() else None
                data = redact(data)
                if postprocess:
                    data = postprocess(data)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                status = "FAILED"
                error = f"Invalid response: {exc}"
        else:
            status = classify_error(completed.stderr, completed.returncode)
            error = completed.stderr.strip()[-4000:] or f"gh api exit={completed.returncode}"
        ok = status == "VERIFIED"
        path = raw_path or self.raw_dir / f"{safe_slug(name)}.json"
        write_json(
            path,
            {
                "_audit": {
                    "name": name,
                    "endpoint": endpoint,
                    "status": status,
                    "fetched_at": iso_now(),
                    "duration_ms": duration_ms,
                    "returncode": completed.returncode,
                    "error": error,
                },
                "data": data if ok else None,
            },
        )
        count = None
        if isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict) and isinstance(data.get("total_count"), int):
            count = int(data["total_count"])
        self._record(
            name=name,
            endpoint=endpoint,
            status=status,
            ok=ok,
            count=count,
            duration_ms=duration_ms,
            returncode=completed.returncode,
            error=error,
            raw_path=path,
        )
        if ok:
            self.datasets[name] = data
            return data
        return None

    def get_list(
        self,
        name: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        item_key: str | None = None,
        max_items: int | None = None,
        postprocess: Callable[[Any], Any] | None = None,
        raw_path: Path | None = None,
    ) -> list[Any] | None:
        started = time.monotonic()
        limit = max_items or self.max_items
        per_page = min(100, limit)
        page = 1
        items: list[Any] = []
        status = "VERIFIED"
        error: str | None = None
        returncode = 0
        while True:
            page_params = dict(params or {})
            page_params.update({"page": page, "per_page": per_page})
            self.api_calls += 1
            completed = self.run_command(self._command(endpoint, page_params))
            returncode = completed.returncode
            if completed.returncode != 0:
                status = classify_error(completed.stderr, completed.returncode)
                error = completed.stderr.strip()[-4000:]
                break
            try:
                payload = json.loads(completed.stdout) if completed.stdout.strip() else []
            except json.JSONDecodeError as exc:
                status = "FAILED"
                error = f"Invalid JSON page {page}: {exc}"
                break
            page_items = payload if item_key is None else payload.get(item_key, [])
            if not isinstance(page_items, list):
                status = "FAILED"
                error = f"Expected list at item_key={item_key!r}, page={page}"
                break
            items.extend(page_items)
            if len(page_items) < per_page:
                break
            if len(items) >= limit or page >= self.max_pages:
                items = items[:limit]
                status = "VERIFIED_TRUNCATED"
                break
            page += 1
        duration_ms = round((time.monotonic() - started) * 1000)
        ok = status.startswith("VERIFIED")
        safe_items = redact(items)
        if ok and postprocess:
            safe_items = postprocess(safe_items)
        path = raw_path or self.raw_dir / f"{safe_slug(name)}.json"
        write_json(
            path,
            {
                "_audit": {
                    "name": name,
                    "endpoint": endpoint,
                    "status": status,
                    "fetched_at": iso_now(),
                    "duration_ms": duration_ms,
                    "returncode": returncode,
                    "error": error,
                    "pages_requested": page,
                    "max_items": limit,
                },
                "data": safe_items if ok else None,
            },
        )
        self._record(
            name=name,
            endpoint=endpoint,
            status=status,
            ok=ok,
            count=len(safe_items) if ok else None,
            duration_ms=duration_ms,
            returncode=returncode,
            error=error,
            raw_path=path,
        )
        if ok:
            self.datasets[name] = safe_items
            return safe_items
        return None

    def graphql_review_threads(
        self,
        *,
        owner: str,
        repo_name: str,
        number: int,
        raw_path: Path,
    ) -> list[Any] | None:
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
            f"owner={owner}",
            "-F",
            f"name={repo_name}",
            "-F",
            f"number={number}",
        ]
        started = time.monotonic()
        self.api_calls += 1
        completed = self.run_command(command)
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
        self._record(
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
        if ok:
            return threads
        return None

    def status_for(self, name: str) -> str | None:
        for record in reversed(self.records):
            if record.name == name:
                return record.status
        return None
