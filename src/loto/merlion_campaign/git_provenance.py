from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from loto.merlion_campaign.bootstrap_resume import (
    _canonical_sha256,
    _validate_hash_bound_payload,
    write_json,
)

GIT_PROVENANCE_SCHEMA = "merlion-bootstrap-git-provenance-v1"


def parse_git_porcelain_z(data: bytes) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    fields = data.decode("utf-8", errors="strict").split("\0")
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        if len(field) < 4 or field[2] != " ":
            raise ValueError("git porcelain output is invalid")
        status = field[:2]
        path = field[3:]
        record = {"status": status, "path": path}
        if status[0] in {"R", "C"}:
            if index >= len(fields) or not fields[index]:
                raise ValueError("git porcelain rename source is missing")
            record["source_path"] = fields[index]
            index += 1
        entries.append(record)
    return entries


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> bytes:
    completed = runner(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git command failed: {' '.join(arguments)}: {stderr}")
    return completed.stdout


def probe_git_state(
    root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    root = root.resolve()
    head = _run_git(root, ["rev-parse", "HEAD"], runner=runner).decode("ascii").strip()
    branch = _run_git(
        root,
        ["rev-parse", "--abbrev-ref", "HEAD"],
        runner=runner,
    ).decode("utf-8").strip()
    status = _run_git(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        runner=runner,
    )
    return {
        "head_sha": head,
        "branch": branch,
        "changes": parse_git_porcelain_z(status),
    }


def build_git_provenance(
    root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    state = probe_git_state(root, runner=runner)
    blockers: list[str] = []
    if len(str(state["head_sha"])) != 40:
        blockers.append("GIT_HEAD_INVALID")
    if state["branch"] == "HEAD":
        blockers.append("GIT_DETACHED_HEAD")
    if state["changes"]:
        blockers.append("GIT_WORKTREE_NOT_CLEAN")
    report: dict[str, Any] = {
        "schema_version": GIT_PROVENANCE_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "CLEAN" if not blockers else "BLOCKED",
        "root": str(root.resolve()),
        "head_sha": state["head_sha"],
        "branch": state["branch"],
        "changes": state["changes"],
        "blockers": blockers,
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def validate_git_provenance(
    payload: Mapping[str, Any],
    *,
    require_clean: bool,
) -> None:
    if payload.get("schema_version") != GIT_PROVENANCE_SCHEMA:
        raise ValueError("unsupported Git provenance schema")
    _validate_hash_bound_payload(payload, hash_field="report_sha256")
    head = payload.get("head_sha")
    if not isinstance(head, str) or len(head) != 40:
        raise ValueError("Git provenance head SHA is invalid")
    if any(value not in "0123456789abcdef" for value in head):
        raise ValueError("Git provenance head SHA is invalid")
    changes = payload.get("changes")
    if not isinstance(changes, list):
        raise ValueError("Git provenance changes are invalid")
    if require_clean and payload.get("status") != "CLEAN":
        raise ValueError("Git provenance is not CLEAN")
    if require_clean and changes:
        raise ValueError("Git provenance contains worktree changes")


def write_git_provenance(path: Path, payload: Mapping[str, Any]) -> None:
    write_json(path, payload)
