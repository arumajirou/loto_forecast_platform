from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from loto.basicts_campaign.formal_verification import (
    FormalVerificationError,
    verify_formal_bundle,
    verify_recursive_sha256,
)

COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CHECKSUM_LINE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<name>[^/\\]+)$")


class FormalReceiptError(FormalVerificationError):
    """Raised when a formal verification receipt is unsafe or inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _require_commit(value: str) -> str:
    if COMMIT_PATTERN.fullmatch(value) is None:
        raise FormalReceiptError(f"expected Git commit is invalid: {value!r}")
    return value


def _required_regular_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise FormalReceiptError(f"required regular file is missing or unsafe: {path}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    _required_regular_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalReceiptError(f"cannot parse JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FormalReceiptError(f"JSON must contain an object: {path}")
    return payload


def _bundle_fingerprint(checksums: dict[str, str]) -> str:
    if not checksums:
        raise FormalReceiptError("source bundle checksum map is empty")
    valid_items = all(
        isinstance(path, str) and isinstance(digest, str) for path, digest in checksums.items()
    )
    if not valid_items:
        raise FormalReceiptError("source bundle checksum map is invalid")
    return _canonical_sha256(checksums)


def build_formal_receipt(run_dir: Path, *, expected_git_commit: str) -> dict[str, Any]:
    """Re-verify a formal bundle and build a deterministic external receipt."""

    expected_commit = _require_commit(expected_git_commit)
    if run_dir.is_symlink():
        raise FormalReceiptError("source bundle path must not be a symbolic link")
    root = run_dir.resolve()
    verification = verify_formal_bundle(root)
    actual_commit = verification.get("git_commit")
    if actual_commit != expected_commit:
        raise FormalReceiptError(
            "formal evidence Git commit mismatch: "
            f"expected {expected_commit}, got {actual_commit!r}"
        )
    checksums = verify_recursive_sha256(root)
    status_path = _required_regular_file(root / "FORMAL_P0_STATUS.json")
    manifest_path = _required_regular_file(root / "FORMAL_P0_MANIFEST.json")
    sums_path = _required_regular_file(root / "SHA256SUMS")
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "BASICTS_FORMAL_P0_VERIFICATION_RECEIPT",
        "evidence_only": True,
        "expected_git_commit": expected_commit,
        "source_bundle": {
            "path": str(root),
            "formal_status_sha256": _sha256(status_path),
            "formal_manifest_sha256": _sha256(manifest_path),
            "sha256sums_sha256": _sha256(sums_path),
            "bundle_fingerprint_sha256": _bundle_fingerprint(checksums),
            "checksum_entries": len(checksums),
        },
        "verification_report_sha256": _canonical_sha256(verification),
        "verification": verification,
        "not_certified": [
            "cryptographic signing or external timestamp authority",
            "re-execution of dependency installation, training, or inference",
            "accuracy improvement or baseline superiority",
        ],
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _receipt_output_path(run_dir: Path, output: Path) -> Path:
    if run_dir.is_symlink():
        raise FormalReceiptError("source bundle path must not be a symbolic link")
    if output.is_symlink():
        raise FormalReceiptError("receipt output path is a symbolic link")
    root = run_dir.resolve()
    candidate = output.resolve()
    checksum = candidate.with_suffix(candidate.suffix + ".sha256")
    if candidate == root or candidate.is_relative_to(root):
        raise FormalReceiptError("receipt output must be outside the source bundle")
    if candidate.is_symlink() or checksum.is_symlink():
        raise FormalReceiptError("receipt output path is a symbolic link")
    if candidate.exists() or checksum.exists():
        raise FormalReceiptError(f"receipt output already exists: {candidate}")
    return candidate


def write_formal_receipt(
    run_dir: Path,
    output: Path,
    *,
    expected_git_commit: str,
) -> Path:
    """Write a deterministic receipt and a detached SHA-256 file."""

    destination = _receipt_output_path(run_dir, output)
    receipt = build_formal_receipt(
        run_dir,
        expected_git_commit=expected_git_commit,
    )
    _atomic_write_text(
        destination,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(
        destination.with_suffix(destination.suffix + ".sha256"),
        f"{_sha256(destination)}  {destination.name}\n",
    )
    return destination


def _verify_receipt_checksum(receipt_path: Path) -> str:
    checksum_input = receipt_path.with_suffix(receipt_path.suffix + ".sha256")
    if receipt_path.is_symlink() or checksum_input.is_symlink():
        raise FormalReceiptError("receipt or checksum path is a symbolic link")
    receipt = _required_regular_file(receipt_path.resolve())
    checksum = _required_regular_file(checksum_input.resolve())
    lines = checksum.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise FormalReceiptError("receipt checksum must contain exactly one line")
    match = CHECKSUM_LINE.fullmatch(lines[0])
    if match is None or match.group("name") != receipt.name:
        raise FormalReceiptError("receipt checksum target is invalid")
    actual = _sha256(receipt)
    if match.group("digest") != actual:
        raise FormalReceiptError("receipt SHA-256 mismatch")
    return actual


def verify_formal_receipt(
    run_dir: Path,
    receipt_path: Path,
    *,
    expected_git_commit: str,
) -> dict[str, Any]:
    """Recompute and compare a stored receipt against the current source bundle."""

    _verify_receipt_checksum(receipt_path)
    stored = _load_json(receipt_path.resolve())
    recomputed = build_formal_receipt(
        run_dir,
        expected_git_commit=expected_git_commit,
    )
    if stored != recomputed:
        raise FormalReceiptError("stored receipt differs from recomputed formal evidence")
    return stored


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or verify a BasicTS formal P0 evidence receipt"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "verify"):
        command = subparsers.add_parser(action)
        command.add_argument("--run-dir", type=Path, required=True)
        command.add_argument("--expected-git-commit", required=True)
        command.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "create":
            path = write_formal_receipt(
                args.run_dir,
                args.receipt,
                expected_git_commit=args.expected_git_commit,
            )
            payload = _load_json(path)
        else:
            path = args.receipt.resolve()
            payload = verify_formal_receipt(
                args.run_dir,
                path,
                expected_git_commit=args.expected_git_commit,
            )
    except FormalVerificationError as exc:
        print(
            f"BASICTS_FORMAL_P0_RECEIPT=FAILED\nERROR={type(exc).__name__}: {exc}",
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"BASICTS_FORMAL_P0_RECEIPT=PASS\nRECEIPT={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
