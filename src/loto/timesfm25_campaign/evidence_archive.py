from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from loto.timesfm25_campaign.certification_bundle import sha256_file, validate_run_id


class EvidenceReviewError(ValueError):
    """Raised when an evidence archive is unsafe or externally invalid."""


def verify_archive_sidecar(archive_path: Path, sidecar_path: Path) -> str:
    archive = archive_path.resolve()
    sidecar = sidecar_path.resolve()
    if not archive.is_file():
        raise EvidenceReviewError(f"archive is missing: {archive}")
    if not sidecar.is_file():
        raise EvidenceReviewError(f"archive SHA-256 sidecar is missing: {sidecar}")
    lines = [line for line in sidecar.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 1:
        raise EvidenceReviewError("archive SHA-256 sidecar must contain exactly one entry")
    try:
        expected, filename = lines[0].split("  ", 1)
    except ValueError as exc:
        raise EvidenceReviewError("archive SHA-256 sidecar has invalid format") from exc
    expected = expected.lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise EvidenceReviewError("archive SHA-256 sidecar digest is invalid")
    if filename != archive.name:
        raise EvidenceReviewError("archive SHA-256 sidecar filename does not match")
    actual = sha256_file(archive)
    if actual != expected:
        raise EvidenceReviewError("archive SHA-256 does not match sidecar")
    return actual


def inspect_archive(
    archive_path: Path,
    *,
    max_files: int = 1024,
    max_member_bytes: int = 1024 * 1024 * 1024,
    max_total_bytes: int = 2 * 1024 * 1024 * 1024,
    max_compression_ratio: float = 200.0,
) -> dict[str, Any]:
    if min(max_files, max_member_bytes, max_total_bytes) < 1:
        raise ValueError("archive limits must be positive")
    if max_compression_ratio < 1:
        raise ValueError("max_compression_ratio must be >= 1")

    seen: set[str] = set()
    roots: set[str] = set()
    total = 0
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if not members:
            raise EvidenceReviewError("archive is empty")
        if len(members) > max_files:
            raise EvidenceReviewError("archive contains too many members")
        for info in members:
            name = info.filename
            if name in seen:
                raise EvidenceReviewError(f"duplicate ZIP member: {name}")
            seen.add(name)
            if info.is_dir() or info.flag_bits & 0x1:
                raise EvidenceReviewError(f"unsupported ZIP member: {name}")
            if "\\" in name or name.startswith("/"):
                raise EvidenceReviewError(f"unsafe ZIP member path: {name}")
            parts = name.split("/")
            if len(parts) < 2 or any(part in {"", ".", ".."} for part in parts):
                raise EvidenceReviewError(f"unsafe ZIP member path: {name}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise EvidenceReviewError(f"symlink ZIP member is not allowed: {name}")
            if info.file_size > max_member_bytes:
                raise EvidenceReviewError(f"ZIP member exceeds size limit: {name}")
            total += info.file_size
            if total > max_total_bytes:
                raise EvidenceReviewError("archive exceeds total uncompressed size limit")
            if info.file_size and info.compress_size == 0:
                raise EvidenceReviewError(f"ZIP member has impossible compression size: {name}")
            if info.compress_size and info.file_size / info.compress_size > max_compression_ratio:
                raise EvidenceReviewError(f"ZIP member exceeds compression ratio limit: {name}")
            roots.add(PurePosixPath(*parts).parts[0])

    if len(roots) != 1:
        raise EvidenceReviewError("archive must contain exactly one top-level Run ID")
    return {
        "run_id": validate_run_id(next(iter(roots))),
        "member_count": len(seen),
        "total_uncompressed_bytes": total,
    }


def safe_extract_archive(archive_path: Path, destination: Path, run_id: str) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            if relative.parts[0] != run_id:
                raise EvidenceReviewError("ZIP top-level directory changed after inspection")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if target.stat().st_size != info.file_size:
                raise EvidenceReviewError(f"extracted size mismatch: {info.filename}")
    return destination / run_id
