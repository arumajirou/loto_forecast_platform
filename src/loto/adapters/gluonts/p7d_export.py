from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from .p7d_common import (
    CHECKSUM_NAME,
    COMPLETE_NAME,
    MANIFEST_NAME,
    sha256_file,
    utc_now,
)
from .p7d_contract import (
    P7DBundleEntry,
    P7DBundleManifest,
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_bytes,
)
from .p7d_validation import verify_run_root


def _payload_entries(run_root: Path) -> list[P7DBundleEntry]:
    return [
        P7DBundleEntry(
            path=f"run/{path.relative_to(run_root).as_posix()}",
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(run_root.rglob("*"))
        if path.is_file()
    ]


def _metadata_payloads(
    manifest: P7DBundleManifest,
) -> tuple[bytes, bytes, bytes]:
    manifest_bytes = canonical_json_bytes(manifest.model_dump(mode="json"))
    complete_bytes = (
        f"RUN_ID={manifest.run_id}\n"
        f"COMMIT_SHA={manifest.source_commit_sha}\n"
        f"P8_ELIGIBLE={str(manifest.p8_eligible).lower()}\n"
    ).encode("utf-8")
    lines = [f"{entry.sha256}  {entry.path}" for entry in manifest.entries]
    lines.extend(
        (
            f"{sha256_bytes(manifest_bytes)}  {MANIFEST_NAME}",
            f"{sha256_bytes(complete_bytes)}  {COMPLETE_NAME}",
        )
    )
    checksum_bytes = ("\n".join(sorted(lines)) + "\n").encode("utf-8")
    return manifest_bytes, complete_bytes, checksum_bytes


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.flag_bits = 0
    return info


def create_evidence_bundle(
    run_root: Path,
    archive_path: Path,
) -> tuple[P7DBundleManifest, str]:
    run_root = run_root.resolve()
    archive_path = archive_path.resolve()
    if run_root == archive_path or run_root in archive_path.parents:
        raise ValueError("P7D archive must be outside the immutable run directory")
    sidecar = archive_path.with_suffix(archive_path.suffix + ".sha256")
    if archive_path.exists() or sidecar.exists():
        raise ValueError("P7D archive and sidecar must not already exist")
    if archive_path.suffix.lower() != ".zip":
        raise ValueError("P7D archive path must end in .zip")
    context = verify_run_root(run_root)
    entries = _payload_entries(run_root)
    manifest = P7DBundleManifest(
        run_id=context["run_id"],
        source_commit_sha=context["commit_sha"],
        created_at_utc=utc_now(),
        p7b_execution_manifest_sha256=context["execution_manifest_sha256"],
        p7b_execution_checksum_sha256=context["execution_checksum_sha256"],
        p7c_manifest_sha256=context["manifest_sha256"],
        p7c_checksum_sha256=context["checksum_sha256"],
        orchestration_checksum_sha256=context["orchestration_checksum_sha256"],
        audit_sha256=context["audit_sha256"],
        failure_matrix_sha256=context["failure_matrix_sha256"],
        p7b_return_code=context["p7b_return_code"],
        p7c_return_code=context["p7c_return_code"],
        evidence_state=context["evidence_state"],
        certification_status=context["certification_status"],
        verified_model_lifecycles=context["verified_model_lifecycles"],
        p8_eligible=context["p8_eligible"],
        entries=entries,
    )
    manifest_bytes, complete_bytes, checksum_bytes = _metadata_payloads(manifest)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{archive_path.name}.",
        suffix=".tmp",
        dir=archive_path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for entry in entries:
                source = run_root / entry.path.removeprefix("run/")
                with source.open("rb") as source_handle:
                    with archive.open(_zip_info(entry.path), "w") as target:
                        shutil.copyfileobj(source_handle, target, 1024 * 1024)
            archive.writestr(_zip_info(MANIFEST_NAME), manifest_bytes)
            archive.writestr(_zip_info(COMPLETE_NAME), complete_bytes)
            archive.writestr(_zip_info(CHECKSUM_NAME), checksum_bytes)
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)
    archive_sha = sha256_file(archive_path)
    atomic_write_bytes(
        sidecar,
        f"{archive_sha}  {archive_path.name}\n".encode("utf-8"),
    )
    return manifest, archive_sha
