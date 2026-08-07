from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalAuthorizationError,
    P17EligibilityEvidence,
    canonical_json_bytes,
    canonical_sha256,
)

P17_REQUIRED_FILES = {
    "REQUEST_METADATA.json",
    "UPSTREAM_LINEAGE.json",
    "WINDOW_EVIDENCE.json",
    "AGGREGATED_METRICS.json",
    "RULE_EVALUATION.json",
    "PROMOTION_DECISION.json",
    "response.json",
    "ARTIFACT_MANIFEST.json",
    "SHA256SUMS",
}



def read_allowed_signers_inventory(path: Path) -> tuple[str, ...]:
    resolved = path.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise ApprovalAuthorizationError(
            "ALLOWED_SIGNERS_FILE_INVALID",
            str(resolved),
        )
    identities: list[str] = []
    key_blobs: list[str] = []
    for raw_line in resolved.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 3:
            raise ApprovalAuthorizationError("ALLOWED_SIGNERS_LINE_INVALID", line)
        identity, key_type, key_blob = fields[:3]
        if not re.fullmatch(r"[A-Za-z0-9._@-]+", identity):
            raise ApprovalAuthorizationError(
                "ALLOWED_SIGNER_IDENTITY_INVALID",
                identity,
            )
        if "," in identity:
            raise ApprovalAuthorizationError(
                "ALLOWED_SIGNER_MULTIPLE_PRINCIPALS_FORBIDDEN",
                identity,
            )
        if key_type != "ssh-ed25519":
            raise ApprovalAuthorizationError(
                "ALLOWED_SIGNER_KEY_TYPE_INVALID",
                key_type,
            )
        try:
            decoded = base64.b64decode(key_blob, validate=True)
        except ValueError as exc:
            raise ApprovalAuthorizationError(
                "ALLOWED_SIGNER_KEY_INVALID",
                identity,
            ) from exc
        if not decoded:
            raise ApprovalAuthorizationError(
                "ALLOWED_SIGNER_KEY_INVALID",
                identity,
            )
        identities.append(identity)
        key_blobs.append(key_blob)
    if len(identities) != 2:
        raise ApprovalAuthorizationError(
            "ALLOWED_SIGNER_COUNT_MISMATCH",
            str(len(identities)),
        )
    if len(set(identities)) != len(identities):
        raise ApprovalAuthorizationError(
            "ALLOWED_SIGNER_IDENTITY_DUPLICATE",
            str(identities),
        )
    if len(set(key_blobs)) != len(key_blobs):
        raise ApprovalAuthorizationError(
            "ALLOWED_SIGNER_KEY_DUPLICATE",
            str(identities),
        )
    return tuple(identities)

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApprovalAuthorizationError("JSON_READ_FAILED", str(path)) from exc
    if not isinstance(payload, dict):
        raise ApprovalAuthorizationError("JSON_OBJECT_REQUIRED", str(path))
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def empty_output_dir(path: Path) -> Path:
    root = path.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ApprovalAuthorizationError("OUTPUT_NOT_EMPTY", str(root))
    root.mkdir(parents=True, exist_ok=True)
    return root


def assert_regular_tree(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise ApprovalAuthorizationError("EVIDENCE_DIRECTORY_MISSING", str(root))
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ApprovalAuthorizationError("SYMLINK_FORBIDDEN", str(path))
        if path.is_dir():
            continue
        if not path.is_file():
            raise ApprovalAuthorizationError("SPECIAL_FILE_FORBIDDEN", str(path))
        files.append(path)
    return files


def tree_sha256(root: Path) -> str:
    root = root.resolve()
    parts: list[bytes] = []
    for path in assert_regular_tree(root):
        parts.append(path.relative_to(root).as_posix().encode("utf-8"))
        parts.append(path.read_bytes())
    return hashlib.sha256(b"\0".join(parts)).hexdigest()


def verify_sha256sums(root: Path) -> set[str]:
    root = root.resolve()
    files = assert_regular_tree(root)
    observed = {path.relative_to(root).as_posix() for path in files}
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise ApprovalAuthorizationError("SHA256SUMS_MISSING", str(root))
    entries: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise ApprovalAuthorizationError("SHA256SUMS_INVALID", line) from exc
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ApprovalAuthorizationError("SHA256_PATH_UNSAFE", relative)
        if relative in entries:
            raise ApprovalAuthorizationError("SHA256_DUPLICATE_ENTRY", relative)
        entries[relative] = digest
    expected = observed - {"SHA256SUMS"}
    if set(entries) != expected:
        raise ApprovalAuthorizationError(
            "SHA256_COVERAGE_MISMATCH",
            str(sorted(set(entries) ^ expected)),
        )
    for relative, digest in entries.items():
        if len(digest) != 64 or file_sha256(root / relative) != digest:
            raise ApprovalAuthorizationError("SHA256_MISMATCH", relative)
    return observed


def verify_manifest(root: Path, expected_payloads: set[str]) -> None:
    manifest = load_json(root / "ARTIFACT_MANIFEST.json")
    records = manifest.get("files")
    if not isinstance(records, list):
        raise ApprovalAuthorizationError("MANIFEST_FILES_INVALID", str(root))
    by_path: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ApprovalAuthorizationError("MANIFEST_RECORD_INVALID", str(record))
        relative = record["path"]
        if relative in by_path:
            raise ApprovalAuthorizationError("MANIFEST_DUPLICATE_ENTRY", relative)
        by_path[relative] = record
    if set(by_path) != expected_payloads:
        raise ApprovalAuthorizationError(
            "MANIFEST_COVERAGE_MISMATCH",
            str(sorted(set(by_path) ^ expected_payloads)),
        )
    for relative, record in by_path.items():
        path = root / relative
        if record.get("bytes") != path.stat().st_size:
            raise ApprovalAuthorizationError("MANIFEST_SIZE_MISMATCH", relative)
        if record.get("sha256") != file_sha256(path):
            raise ApprovalAuthorizationError("MANIFEST_HASH_MISMATCH", relative)


def write_evidence(root: Path, payload_names: Sequence[str]) -> None:
    payloads = sorted(set(payload_names))
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": name,
                "bytes": (root / name).stat().st_size,
                "sha256": file_sha256(root / name),
            }
            for name in payloads
        ],
    }
    write_json(root / "ARTIFACT_MANIFEST.json", manifest)
    lines = []
    for path in sorted(root.iterdir()):
        if path.name == "SHA256SUMS":
            continue
        if path.is_symlink() or not path.is_file():
            raise ApprovalAuthorizationError("NON_REGULAR_OUTPUT", str(path))
        lines.append(f"{file_sha256(path)}  {path.name}")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_p17_eligibility(root: Path) -> P17EligibilityEvidence:
    root = root.resolve()
    observed = verify_sha256sums(root)
    if observed != P17_REQUIRED_FILES:
        raise ApprovalAuthorizationError(
            "P17_FILE_SET_MISMATCH",
            str(sorted(observed)),
        )
    verify_manifest(root, P17_REQUIRED_FILES - {"ARTIFACT_MANIFEST.json", "SHA256SUMS"})
    decision = load_json(root / "PROMOTION_DECISION.json")
    response = load_json(root / "response.json")
    decision_hash = str(decision.get("decision_sha256", ""))
    decision_core = dict(decision)
    decision_core.pop("decision_sha256", None)
    if decision_hash != canonical_sha256(decision_core):
        raise ApprovalAuthorizationError(
            "P17_DECISION_HASH_MISMATCH",
            decision_hash,
        )
    expected_response = {
        "status": decision.get("status"),
        "decision": decision.get("decision"),
        "reason_code": decision.get("reason_code"),
        "selected_candidate_id": decision.get("selected_candidate_id"),
        "registry_write_allowed": False,
    }
    if response != expected_response:
        raise ApprovalAuthorizationError("P17_RESPONSE_MISMATCH", str(root))
    request = load_json(root / "REQUEST_METADATA.json")
    payload = {
        "schema_version": "1.0",
        "p17_bundle_sha256": tree_sha256(root),
        "p17_decision_sha256": decision_hash,
        "p17_run_id": request.get("run_id"),
        "selected_candidate_id": decision.get("selected_candidate_id"),
        "decision": decision.get("decision"),
        "status": decision.get("status"),
        "reason_code": decision.get("reason_code"),
        "human_approval_required": decision.get("human_approval_required"),
        "human_approval_granted": decision.get("human_approval_granted"),
        "automatic_promotion": decision.get("automatic_promotion"),
        "automatic_retraining": decision.get("automatic_retraining"),
        "registry_write_allowed": decision.get("registry_write_allowed"),
        "promotion_status": decision.get("promotion_status"),
    }
    try:
        return P17EligibilityEvidence.model_validate(payload)
    except Exception as exc:
        raise ApprovalAuthorizationError("P17_NOT_ELIGIBLE", str(exc)) from exc


def approval_output_tree_sha256(root: Path) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            [
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": file_sha256(path),
                }
                for path in assert_regular_tree(root)
            ]
        )
    ).hexdigest()


__all__ = [
    "P17_REQUIRED_FILES",
    "approval_output_tree_sha256",
    "empty_output_dir",
    "file_sha256",
    "load_json",
    "read_allowed_signers_inventory",
    "read_p17_eligibility",
    "tree_sha256",
    "verify_manifest",
    "verify_sha256sums",
    "write_evidence",
    "write_json",
]
