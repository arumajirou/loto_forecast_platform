from __future__ import annotations

import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .p7d_common import (
    CHECKSUM_NAME,
    COMPLETE_NAME,
    MANIFEST_NAME,
    MAX_ARCHIVE_MEMBERS,
    MAX_CHECKSUM_BYTES,
    MAX_COMPRESSION_RATIO,
    MAX_MANIFEST_BYTES,
    MAX_MEMBER_UNCOMPRESSED_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    METADATA_NAMES,
    P7DBundleError,
    _hash_stream,
    _safe_relative,
    sha256_file,
    utc_now,
)
from .p7d_contract import (
    P7DBundleManifest,
    P7DVerificationReport,
    atomic_write_bytes,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
)
from .p7d_validation import verify_run_root


def _validate_zip_name(name: str) -> None:
    path = _safe_relative(name)
    if name.endswith("/") or len(path.parts) == 0:
        raise P7DBundleError(f"directory member is not permitted: {name}")


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _parse_marker_bytes(payload: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in payload.decode("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def _parse_checksum_bytes(payload: bytes) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise P7DBundleError(f"invalid P7D checksum line {line_number}")
        digest, name = parts
        _validate_zip_name(name)
        if name in entries:
            raise P7DBundleError(f"duplicate P7D checksum path: {name}")
        entries[name] = digest.lower()
    return entries


def _inspect_archive(
    archive_path: Path,
) -> tuple[P7DBundleManifest, str, str, int]:
    archive_sha = sha256_file(archive_path)
    with zipfile.ZipFile(archive_path, "r", allowZip64=True) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise P7DBundleError("ZIP member count exceeds the safety limit")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise P7DBundleError("ZIP contains duplicate member names")
        declared_total = 0
        for info in infos:
            _validate_zip_name(info.filename)
            if info.flag_bits & 0x3:
                raise P7DBundleError("encrypted ZIP members are not permitted")
            if _zip_member_is_symlink(info):
                raise P7DBundleError("symlink ZIP members are not permitted")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise P7DBundleError("unsupported ZIP compression method")
            if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise P7DBundleError("ZIP member exceeds the safety size limit")
            declared_total += info.file_size
            if declared_total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise P7DBundleError("ZIP exceeds the total safety size limit")
            compressed = max(info.compress_size, 1)
            if info.file_size > compressed * MAX_COMPRESSION_RATIO:
                raise P7DBundleError("ZIP member compression ratio is unsafe")
        if not METADATA_NAMES.issubset(names):
            raise P7DBundleError("P7D metadata members are incomplete")
        manifest_info = archive.getinfo(MANIFEST_NAME)
        checksum_info = archive.getinfo(CHECKSUM_NAME)
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise P7DBundleError("P7D manifest exceeds the safety limit")
        if checksum_info.file_size > MAX_CHECKSUM_BYTES:
            raise P7DBundleError("P7D checksum file exceeds the safety limit")
        manifest_bytes = archive.read(MANIFEST_NAME)
        manifest = P7DBundleManifest.model_validate_json(manifest_bytes)
        complete_values = _parse_marker_bytes(archive.read(COMPLETE_NAME))
        expected_complete = {
            "RUN_ID": manifest.run_id,
            "COMMIT_SHA": manifest.source_commit_sha,
            "P8_ELIGIBLE": str(manifest.p8_eligible).lower(),
        }
        if complete_values != expected_complete:
            raise P7DBundleError("P7D completion marker differs from the manifest")
        expected_names = {entry.path for entry in manifest.entries} | METADATA_NAMES
        if set(names) != expected_names:
            raise P7DBundleError("ZIP member inventory differs from the manifest")
        checksum_bytes = archive.read(CHECKSUM_NAME)
        checksums = _parse_checksum_bytes(checksum_bytes)
        if set(checksums) != expected_names - {CHECKSUM_NAME}:
            raise P7DBundleError("P7D checksum inventory is incomplete or stale")
        entry_map = {entry.path: entry for entry in manifest.entries}
        total = 0
        for name in sorted(expected_names - {CHECKSUM_NAME}):
            with archive.open(name, "r") as handle:
                digest, size = _hash_stream(handle)
            if checksums[name] != digest:
                raise P7DBundleError(f"P7D checksum mismatch: {name}")
            if name in entry_map:
                entry = entry_map[name]
                if entry.sha256 != digest or entry.size_bytes != size:
                    raise P7DBundleError(f"manifest entry mismatch: {name}")
                total += size
        return (
            manifest,
            archive_sha,
            sha256_bytes(checksum_bytes),
            total,
        )


def _extract_archive(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path, "r", allowZip64=True) as archive:
        for info in archive.infolist():
            target = destination / Path(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)


def verify_evidence_bundle(archive_path: Path) -> P7DVerificationReport:
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    manifest, archive_sha, checksum_sha, total = _inspect_archive(archive_path)
    with tempfile.TemporaryDirectory(prefix="gluonts-p7d-verify-") as temporary:
        root = Path(temporary)
        _extract_archive(archive_path, root)
        context = verify_run_root(root / "run")
    comparisons = {
        "run_id": context["run_id"],
        "source_commit_sha": context["commit_sha"],
        "p7b_execution_manifest_sha256": context["execution_manifest_sha256"],
        "p7b_execution_checksum_sha256": context["execution_checksum_sha256"],
        "p7c_manifest_sha256": context["manifest_sha256"],
        "p7c_checksum_sha256": context["checksum_sha256"],
        "orchestration_checksum_sha256": context["orchestration_checksum_sha256"],
        "audit_sha256": context["audit_sha256"],
        "failure_matrix_sha256": context["failure_matrix_sha256"],
        "p7b_return_code": context["p7b_return_code"],
        "p7c_return_code": context["p7c_return_code"],
        "evidence_state": context["evidence_state"],
        "certification_status": context["certification_status"],
        "verified_model_lifecycles": context["verified_model_lifecycles"],
        "p8_eligible": context["p8_eligible"],
    }
    for field, actual in comparisons.items():
        if getattr(manifest, field) != actual:
            raise P7DBundleError(f"nested evidence differs from manifest: {field}")
    return P7DVerificationReport(
        archive_path=str(archive_path),
        archive_sha256=archive_sha,
        bundle_manifest_sha256=sha256_bytes(canonical_json_bytes(manifest.model_dump(mode="json"))),
        bundle_checksum_sha256=checksum_sha,
        run_id=manifest.run_id,
        source_commit_sha=manifest.source_commit_sha,
        entry_count=len(manifest.entries),
        total_payload_bytes=total,
        evidence_state=manifest.evidence_state,
        certification_status=manifest.certification_status,
        verified_model_lifecycles=manifest.verified_model_lifecycles,
        p8_eligible=manifest.p8_eligible,
        verified_at_utc=utc_now(),
    )


def verify_and_extract_bundle(
    archive_path: Path,
    output_dir: Path,
) -> P7DVerificationReport:
    archive_path = archive_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("P7D verification output must be absent or empty")
    report = verify_evidence_bundle(archive_path)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        _extract_archive(archive_path, temporary)
        report_path = temporary / "p7d_verification_report.json"
        atomic_write_json(report_path, report.model_dump(mode="json"))
        sums_path = temporary / "P7D_VERIFY_SHA256SUMS"
        lines = [
            f"{sha256_file(path)}  {path.relative_to(temporary).as_posix()}"
            for path in sorted(temporary.rglob("*"))
            if path.is_file() and path.name != sums_path.name
        ]
        atomic_write_bytes(
            sums_path,
            ("\n".join(lines) + "\n").encode("utf-8"),
        )
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(temporary, output_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return report
