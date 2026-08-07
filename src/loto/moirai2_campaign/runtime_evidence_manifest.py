from __future__ import annotations

from pathlib import Path

from loto.moirai2_campaign.runtime_evidence_common import (
    ManifestVerification,
    RuntimeEvidenceGateError,
    _SHA256_PATTERN,
    _required_file,
    _safe_relative_path,
    load_json_object,
    sha256_file,
)

def parse_sha256_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line:
            continue
        if "  " not in raw_line:
            raise RuntimeEvidenceGateError(
                f"invalid SHA256SUMS line {line_number}: {raw_line!r}"
            )
        digest, relative = raw_line.split("  ", 1)
        if not _SHA256_PATTERN.fullmatch(digest):
            raise RuntimeEvidenceGateError(
                f"invalid SHA-256 at line {line_number}: {digest!r}"
            )
        relative = _safe_relative_path(relative)
        if relative == "SHA256SUMS":
            raise RuntimeEvidenceGateError("SHA256SUMS must not hash itself")
        if relative in entries:
            raise RuntimeEvidenceGateError(
                f"duplicate SHA256SUMS path: {relative}"
            )
        entries[relative] = digest
    if not entries:
        raise RuntimeEvidenceGateError("SHA256SUMS is empty")
    return entries


def verify_campaign_manifest(campaign_dir: Path) -> ManifestVerification:
    root = campaign_dir.resolve()
    manifest_path = _required_file(root, "SHA256SUMS")
    entries = parse_sha256_manifest(manifest_path)
    verified = 0
    for relative, expected in sorted(entries.items()):
        artifact = root / relative
        if not artifact.is_file():
            raise RuntimeEvidenceGateError(
                f"SHA256SUMS artifact is missing: {relative}"
            )
        actual = sha256_file(artifact)
        if actual != expected:
            raise RuntimeEvidenceGateError(
                f"SHA-256 mismatch for {relative}: expected={expected} actual={actual}"
            )
        verified += 1

    artifact_manifest = load_json_object(
        _required_file(root, "ARTIFACT_MANIFEST.json")
    )
    raw_files = artifact_manifest.get("files")
    if not isinstance(raw_files, list) or not all(
        isinstance(item, str) for item in raw_files
    ):
        raise RuntimeEvidenceGateError("artifact manifest files must be text paths")
    artifact_files = [_safe_relative_path(item) for item in raw_files]
    if len(artifact_files) != len(set(artifact_files)):
        raise RuntimeEvidenceGateError("artifact manifest contains duplicate files")
    if int(artifact_manifest.get("file_count", -1)) != len(artifact_files):
        raise RuntimeEvidenceGateError("artifact manifest file_count is inconsistent")
    expected_entries = set(artifact_files) | {"ARTIFACT_MANIFEST.json"}
    if expected_entries != set(entries):
        missing = sorted(set(entries) - expected_entries)
        extra = sorted(expected_entries - set(entries))
        raise RuntimeEvidenceGateError(
            f"artifact manifest and SHA256SUMS differ: missing={missing} extra={extra}"
        )

    actual_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    expected_actual = sorted([*entries, "SHA256SUMS"])
    if actual_files != expected_actual:
        missing = sorted(set(expected_actual) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_actual))
        raise RuntimeEvidenceGateError(
            f"campaign directory contains untracked artifacts: missing={missing} extra={extra}"
        )
    return ManifestVerification(
        manifest_entry_count=len(entries),
        artifact_manifest_file_count=len(artifact_files),
        actual_file_count=len(actual_files),
        verified_file_count=verified,
    )


