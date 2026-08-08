from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOCK_COMMIT_SCHEMA = "merlion-lock-commit-certification-v1"
ADMISSION_SCHEMA = "merlion-lock-admission-v1"
ALLOWED_LOCK_PATH = "environments/merlion-core-py311/uv.lock"
EVIDENCE_INVENTORY_PATH = "run/DEPENDENCY_INVENTORY.csv"


def canonical_sha256(payload: Mapping[str, Any], *, omit: str | None = None) -> str:
    filtered = {key: value for key, value in payload.items() if key != omit}
    encoded = json.dumps(filtered, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    temporary.replace(path)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _run_git(
    root: Path,
    arguments: Sequence[str],
    *,
    check: bool = True,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> subprocess.CompletedProcess[bytes]:
    completed = runner(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git command failed: {' '.join(arguments)}: {stderr}")
    return completed


def _git_text(root: Path, arguments: Sequence[str]) -> str:
    return _run_git(root, arguments).stdout.decode("utf-8", errors="strict").strip()


def _git_bytes(root: Path, arguments: Sequence[str]) -> bytes:
    return _run_git(root, arguments).stdout


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or unsafe")
    data = path.read_bytes()
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload, data


def _validate_admission_report(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_version") != ADMISSION_SCHEMA:
        blockers.append("ADMISSION_SCHEMA_INVALID")
    recorded = payload.get("report_sha256")
    if not isinstance(recorded, str) or len(recorded) != 64:
        blockers.append("ADMISSION_SELF_HASH_MISSING")
    elif recorded != canonical_sha256(payload, omit="report_sha256"):
        blockers.append("ADMISSION_SELF_HASH_MISMATCH")
    if payload.get("status") != "ADMITTED":
        blockers.append("ADMISSION_STATUS_NOT_ADMITTED")
    report_blockers = payload.get("blockers")
    if report_blockers not in ([], None):
        blockers.append("ADMISSION_REPORT_HAS_BLOCKERS")
    if payload.get("lock_path") != ALLOWED_LOCK_PATH:
        blockers.append("ADMISSION_LOCK_PATH_INVALID")
    return blockers


def _parse_status_z(data: bytes) -> list[dict[str, str]]:
    fields = data.decode("utf-8", errors="strict").split("\0")
    records: list[dict[str, str]] = []
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
                raise ValueError("git rename source is missing")
            record["source_path"] = fields[index]
            index += 1
        records.append(record)
    return records


def _probe_commit(root: Path) -> dict[str, Any]:
    head = _git_text(root, ["rev-parse", "HEAD"])
    branch = _git_text(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    parent_line = _git_text(root, ["rev-list", "--parents", "-n", "1", head])
    parent_parts = parent_line.split()
    parents = parent_parts[1:]
    status = _git_bytes(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    )
    changes = _parse_status_z(status)
    return {
        "head_sha": head,
        "branch": branch,
        "parents": parents,
        "worktree_changes": changes,
    }


def _commit_change(root: Path, parent: str, head: str) -> tuple[list[str], str | None]:
    names = _git_bytes(root, ["diff", "--name-only", "-z", parent, head])
    changed_paths = [value for value in names.decode("utf-8").split("\0") if value]
    status_text = _git_text(
        root,
        ["diff", "--name-status", "--no-renames", parent, head, "--", ALLOWED_LOCK_PATH],
    )
    status = None
    if status_text:
        fields = status_text.split("\t", 1)
        if len(fields) == 2 and fields[1] == ALLOWED_LOCK_PATH:
            status = fields[0]
    return changed_paths, status


def _load_evidence_inventory(
    evidence_zip: Path,
    *,
    payload_reader: Callable[[Path], Mapping[str, bytes]],
) -> bytes:
    payloads = payload_reader(evidence_zip)
    inventory = payloads.get(EVIDENCE_INVENTORY_PATH)
    if not isinstance(inventory, bytes):
        raise ValueError("evidence dependency inventory is missing")
    return inventory


def evaluate_lock_commit(
    root: Path,
    admission_report: Path,
    evidence_zip: Path,
    license_review: Path,
    *,
    expected_head: str,
    evidence_verifier: Callable[[Path], Mapping[str, Any]],
    evidence_payload_reader: Callable[[Path], Mapping[str, bytes]],
    license_validator: Callable[
        [Mapping[str, Any], bytes, str, str],
        Sequence[str],
    ],
) -> dict[str, Any]:
    root = root.resolve()
    if admission_report.is_symlink():
        raise ValueError("admission report is missing or unsafe")
    if evidence_zip.is_symlink():
        raise ValueError("evidence ZIP is missing or unsafe")
    if license_review.is_symlink():
        raise ValueError("license review is missing or unsafe")
    admission_report = admission_report.absolute()
    evidence_zip = evidence_zip.absolute()
    license_review = license_review.absolute()
    blockers: list[str] = []
    if len(expected_head) != 40 or any(value not in "0123456789abcdef" for value in expected_head):
        blockers.append("EXPECTED_HEAD_INVALID")

    admission, admission_bytes = _read_json_object(
        admission_report,
        label="admission report",
    )
    blockers.extend(_validate_admission_report(admission))

    git_state = _probe_commit(root)
    actual_head = str(git_state["head_sha"])
    parents = list(git_state["parents"])
    if actual_head != expected_head:
        blockers.append("GIT_HEAD_MISMATCH")
    if git_state["branch"] == "HEAD":
        blockers.append("GIT_DETACHED_HEAD")
    if admission.get("evidence_branch") not in {None, git_state["branch"]}:
        blockers.append("ADMISSION_BRANCH_MISMATCH")
    if git_state["worktree_changes"]:
        blockers.append("GIT_WORKTREE_NOT_CLEAN")
    if len(parents) != 1:
        blockers.append("LOCK_COMMIT_PARENT_COUNT_INVALID")
        parent = None
        changed_paths: list[str] = []
        change_status = None
    else:
        parent = parents[0]
        changed_paths, change_status = _commit_change(root, parent, actual_head)
        if changed_paths != [ALLOWED_LOCK_PATH]:
            blockers.append("LOCK_COMMIT_SCOPE_INVALID")
        if change_status != "A":
            blockers.append("LOCK_COMMIT_STATUS_NOT_ADDED")

    expected_parent = admission.get("expected_head")
    for field in ("actual_head", "evidence_head"):
        if admission.get(field) != expected_parent:
            blockers.append(f"ADMISSION_{field.upper()}_MISMATCH")
    if parent is not None and expected_parent != parent:
        blockers.append("LOCK_COMMIT_PARENT_MISMATCH")

    lock_path = root / ALLOWED_LOCK_PATH
    if not lock_path.is_file() or lock_path.is_symlink():
        blockers.append("COMMITTED_LOCK_MISSING_OR_UNSAFE")
        workspace_lock_sha256 = None
    else:
        workspace_lock_sha256 = sha256_bytes(lock_path.read_bytes())

    if parent is not None:
        parent_has_lock = (
            _run_git(
                root,
                ["cat-file", "-e", f"{parent}:{ALLOWED_LOCK_PATH}"],
                check=False,
            ).returncode
            == 0
        )
        if parent_has_lock:
            blockers.append("LOCK_ALREADY_PRESENT_IN_PARENT")

    blob_sha = None
    committed_lock_sha256 = None
    committed_lock = _run_git(
        root,
        ["show", f"{actual_head}:{ALLOWED_LOCK_PATH}"],
        check=False,
    )
    if committed_lock.returncode != 0:
        blockers.append("LOCK_NOT_PRESENT_IN_COMMIT")
    else:
        committed_lock_sha256 = sha256_bytes(committed_lock.stdout)
        blob_sha = _git_text(root, ["rev-parse", f"{actual_head}:{ALLOWED_LOCK_PATH}"])

    admission_lock_sha = admission.get("lock_sha256")
    for value, code in (
        (workspace_lock_sha256, "WORKSPACE_LOCK_HASH_MISMATCH"),
        (committed_lock_sha256, "COMMITTED_LOCK_HASH_MISMATCH"),
        (admission.get("workspace_lock_sha256"), "ADMISSION_WORKSPACE_LOCK_HASH_MISMATCH"),
    ):
        if value != admission_lock_sha:
            blockers.append(code)

    if not evidence_zip.is_file() or evidence_zip.is_symlink():
        blockers.append("EVIDENCE_ZIP_MISSING_OR_UNSAFE")
        evidence_zip_sha256 = None
        evidence_result: Mapping[str, Any] = {}
    else:
        evidence_zip_sha256 = sha256_bytes(evidence_zip.read_bytes())
        evidence_result = evidence_verifier(evidence_zip)
        if evidence_result.get("status") != "PASS":
            blockers.append("EVIDENCE_VERIFICATION_NOT_PASS")
        if evidence_result.get("evidence_status") != "BOOTSTRAP_PASS":
            blockers.append("EVIDENCE_STATUS_NOT_BOOTSTRAP_PASS")
        if evidence_result.get("zip_sha256") != evidence_zip_sha256:
            blockers.append("EVIDENCE_ZIP_HASH_MISMATCH")
    if admission.get("evidence_zip_sha256") != evidence_zip_sha256:
        blockers.append("ADMISSION_EVIDENCE_HASH_MISMATCH")

    review, review_bytes = _read_json_object(license_review, label="license review")
    if admission.get("license_review_sha256") != sha256_bytes(review_bytes):
        blockers.append("ADMISSION_LICENSE_REVIEW_HASH_MISMATCH")
    if evidence_zip_sha256 is not None and admission_lock_sha is not None:
        inventory = _load_evidence_inventory(
            evidence_zip,
            payload_reader=evidence_payload_reader,
        )
        blockers.extend(
            license_validator(
                review,
                inventory,
                evidence_zip_sha256,
                str(admission_lock_sha),
            )
        )

    report: dict[str, Any] = {
        "schema_version": LOCK_COMMIT_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "LOCK_COMMIT_CERTIFIED" if not blockers else "BLOCKED",
        "commit_sha": actual_head,
        "parent_sha": parent,
        "branch": git_state["branch"],
        "lock_path": ALLOWED_LOCK_PATH,
        "lock_change_status": change_status,
        "changed_paths": changed_paths,
        "lock_blob_sha": blob_sha,
        "lock_sha256": committed_lock_sha256,
        "admission_report_sha256": sha256_bytes(admission_bytes),
        "admission_report_self_hash": admission.get("report_sha256"),
        "evidence_zip_sha256": evidence_zip_sha256,
        "license_review_sha256": sha256_bytes(review_bytes),
        "blockers": sorted(set(blockers)),
        "next_action": (
            "run formal Merlion runtime certification from this exact clean commit"
            if not blockers
            else "resolve every blocker and create a new lock commit certification report"
        ),
    }
    report["report_sha256"] = canonical_sha256(report)
    return report


def validate_lock_commit_report(
    root: Path,
    payload: Mapping[str, Any],
    *,
    expected_head: str,
) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_version") != LOCK_COMMIT_SCHEMA:
        blockers.append("LOCK_COMMIT_REPORT_SCHEMA_INVALID")
    recorded = payload.get("report_sha256")
    if not isinstance(recorded, str) or len(recorded) != 64:
        blockers.append("LOCK_COMMIT_REPORT_SELF_HASH_MISSING")
    elif recorded != canonical_sha256(payload, omit="report_sha256"):
        blockers.append("LOCK_COMMIT_REPORT_SELF_HASH_MISMATCH")
    if payload.get("status") != "LOCK_COMMIT_CERTIFIED":
        blockers.append("LOCK_COMMIT_REPORT_NOT_CERTIFIED")
    if payload.get("blockers") not in ([], None):
        blockers.append("LOCK_COMMIT_REPORT_HAS_BLOCKERS")

    state = _probe_commit(root.resolve())
    if state["head_sha"] != expected_head:
        blockers.append("CURRENT_GIT_HEAD_MISMATCH")
    if payload.get("commit_sha") != expected_head:
        blockers.append("REPORT_GIT_HEAD_MISMATCH")
    if state["branch"] == "HEAD":
        blockers.append("CURRENT_GIT_DETACHED_HEAD")
    if state["worktree_changes"]:
        blockers.append("CURRENT_GIT_WORKTREE_NOT_CLEAN")
    if len(state["parents"]) != 1 or payload.get("parent_sha") != state["parents"][0]:
        blockers.append("CURRENT_GIT_PARENT_MISMATCH")

    lock_path = root.resolve() / ALLOWED_LOCK_PATH
    if not lock_path.is_file() or lock_path.is_symlink():
        blockers.append("CURRENT_LOCK_MISSING_OR_UNSAFE")
    else:
        current_hash = sha256_bytes(lock_path.read_bytes())
        if current_hash != payload.get("lock_sha256"):
            blockers.append("CURRENT_LOCK_HASH_MISMATCH")
    blob = _run_git(
        root.resolve(),
        ["rev-parse", f"HEAD:{ALLOWED_LOCK_PATH}"],
        check=False,
    )
    if blob.returncode != 0:
        blockers.append("CURRENT_LOCK_BLOB_MISSING")
    elif blob.stdout.decode("ascii").strip() != payload.get("lock_blob_sha"):
        blockers.append("CURRENT_LOCK_BLOB_MISMATCH")
    return sorted(set(blockers))


def render_lock_commit_decision(report: Mapping[str, Any]) -> str:
    blockers = report.get("blockers", [])
    blocker_lines = "\n".join(f"- `{value}`" for value in blockers) or "- None"
    return (
        "# Merlion Lock Commit Certification\n\n"
        f"Status: `{report.get('status')}`\n\n"
        f"Commit: `{report.get('commit_sha')}`\n\n"
        f"Parent: `{report.get('parent_sha')}`\n\n"
        f"Lock SHA-256: `{report.get('lock_sha256')}`\n\n"
        "## Blockers\n\n"
        f"{blocker_lines}\n\n"
        "## Next action\n\n"
        f"{report.get('next_action')}\n"
    )
