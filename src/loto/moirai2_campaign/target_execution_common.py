from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "moirai2-p8d-target-execution-v1"
STATE_FILENAME = "P8D_EXECUTION_STATE.json"
PLAN_FILENAME = "P8D_EXECUTION_PLAN.json"
COMMANDS_FILENAME = "P8D_OPERATOR_COMMANDS.md"
MANIFEST_FILENAME = "ARTIFACT_MANIFEST.json"
SHA_FILENAME = "SHA256SUMS"

SUPPORTED_LANE = "supported-py311"
CUDA_LANE = "cuda13-experimental"
LANE_DEVICES = {SUPPORTED_LANE: "cpu", CUDA_LANE: "cuda"}

EVENT_ORDER = (
    "supported_candidate_recorded",
    "supported_installation_recorded",
    "supported_campaign_recorded",
    "cuda_candidate_recorded",
    "cuda_installation_recorded",
    "cuda_campaign_recorded",
    "pair_verification_recorded",
)
STAGES = (
    "INITIALIZED",
    "SUPPORTED_CANDIDATE_RECORDED",
    "SUPPORTED_INSTALLATION_RECORDED",
    "SUPPORTED_CAMPAIGN_RECORDED",
    "CUDA_CANDIDATE_RECORDED",
    "CUDA_INSTALLATION_RECORDED",
    "CUDA_CAMPAIGN_RECORDED",
    "PAIR_VERIFIED",
)


class TargetExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactRecord:
    key: str
    event_type: str
    runtime_lane: str | None
    artifact_dir: str
    artifact_tree_sha256: str
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "event_type": self.event_type,
            "runtime_lane": self.runtime_lane,
            "artifact_dir": self.artifact_dir,
            "artifact_tree_sha256": self.artifact_tree_sha256,
            "summary": self.summary,
        }


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TargetExecutionError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise TargetExecutionError(f"JSON object is required: {path}")
    return payload


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _safe_relative(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise TargetExecutionError(f"artifact escaped root: {path}") from exc
    if not relative or relative.startswith("../"):
        raise TargetExecutionError(f"unsafe artifact path: {relative!r}")
    return relative


def artifact_inventory(root: Path) -> list[dict[str, Any]]:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise TargetExecutionError(f"artifact directory is missing: {resolved}")
    rows: list[dict[str, Any]] = []
    for path in sorted(resolved.rglob("*")):
        if path.is_symlink():
            raise TargetExecutionError(f"symlink is not allowed in evidence: {path}")
        if not path.is_file():
            continue
        rows.append(
            {
                "path": _safe_relative(resolved, path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if not rows:
        raise TargetExecutionError(f"artifact directory is empty: {resolved}")
    return rows


def artifact_tree_sha256(root: Path) -> str:
    return sha256_payload(artifact_inventory(root))


def parse_sha256_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line:
            continue
        if "  " not in line:
            raise TargetExecutionError(f"invalid SHA256SUMS line {line_number}: {line!r}")
        digest, relative = line.split("  ", 1)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise TargetExecutionError(f"invalid SHA-256 at line {line_number}")
        if relative in entries or relative.startswith("/") or ".." in Path(relative).parts:
            raise TargetExecutionError(f"unsafe or duplicate manifest path: {relative}")
        entries[relative] = digest
    if not entries:
        raise TargetExecutionError(f"empty SHA256SUMS: {path}")
    return entries


def verify_sha256_manifest(root: Path) -> dict[str, Any]:
    manifest = root / SHA_FILENAME
    if not manifest.is_file():
        raise TargetExecutionError(f"SHA256SUMS is missing: {root}")
    entries = parse_sha256_manifest(manifest)
    for relative, expected in sorted(entries.items()):
        artifact = root / relative
        if not artifact.is_file():
            raise TargetExecutionError(f"manifest artifact is missing: {relative}")
        actual = sha256_file(artifact)
        if actual != expected:
            raise TargetExecutionError(
                f"SHA-256 mismatch for {relative}: expected={expected} actual={actual}"
            )
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    expected_files = set(entries) | {SHA_FILENAME}
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise TargetExecutionError(f"manifest file set differs: missing={missing} extra={extra}")
    return {
        "entry_count": len(entries),
        "manifest_sha256": sha256_file(manifest),
    }


def verify_control_integrity(control_dir: Path) -> dict[str, Any]:
    root = control_dir.resolve()
    verification = verify_sha256_manifest(root)
    artifact_manifest = load_json_object(root / MANIFEST_FILENAME)
    files = artifact_manifest.get("files")
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise TargetExecutionError("control artifact manifest files are invalid")
    if int(artifact_manifest.get("file_count", -1)) != len(files):
        raise TargetExecutionError("control artifact manifest file_count differs")
    if len(files) != len(set(files)):
        raise TargetExecutionError("control artifact manifest contains duplicates")
    entries = parse_sha256_manifest(root / SHA_FILENAME)
    expected = set(files) | {MANIFEST_FILENAME}
    if set(entries) != expected:
        raise TargetExecutionError("control artifact manifest and SHA256SUMS differ")
    return verification
