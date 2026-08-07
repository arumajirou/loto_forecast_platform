from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Mapping

from loto.merlion_campaign.bootstrap_evidence_contract import (
    EVIDENCE_SCHEMA,
    MANIFEST_NAME,
    SHA256SUMS_NAME,
    safe_archive_name,
    sha256_bytes,
    validate_json_mapping,
    validate_run_evidence,
)
from loto.merlion_campaign.bootstrap_resume import (
    _canonical_sha256,
    _validate_hash_bound_payload,
)

VERIFY_SCHEMA = "merlion-bootstrap-evidence-verification-v1"


def _parse_sha256sums(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in data.decode("utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or len(digest) != 64:
            raise ValueError("SHA256SUMS line is invalid")
        if any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("SHA256SUMS digest is invalid")
        safe_name = safe_archive_name(name)
        if safe_name in result:
            raise ValueError("SHA256SUMS contains a duplicate path")
        result[safe_name] = digest
    return result


def verify_bootstrap_evidence_zip(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [safe_archive_name(info.filename) for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("ZIP contains duplicate paths")
        for info in infos:
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError("ZIP contains a symbolic link")
        payloads = {name: archive.read(name) for name in names}

    if MANIFEST_NAME not in payloads or SHA256SUMS_NAME not in payloads:
        raise ValueError("ZIP is missing manifest or SHA256SUMS")
    manifest = validate_json_mapping(payloads[MANIFEST_NAME], label=MANIFEST_NAME)
    if manifest.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError("unsupported evidence schema")
    _validate_hash_bound_payload(manifest, hash_field="manifest_sha256")

    records = manifest.get("files")
    if not isinstance(records, list):
        raise ValueError("manifest files are invalid")
    expected_names = {MANIFEST_NAME, SHA256SUMS_NAME}
    record_names: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("manifest file record is invalid")
        name = safe_archive_name(str(record.get("path", "")))
        if name in {MANIFEST_NAME, SHA256SUMS_NAME} or name in record_names:
            raise ValueError("manifest contains a reserved or duplicate path")
        record_names.add(name)
        expected_names.add(name)
        data = payloads.get(name)
        if data is None:
            raise ValueError(f"manifest file is missing: {name}")
        if len(data) != record.get("bytes"):
            raise ValueError(f"manifest size mismatch: {name}")
        if sha256_bytes(data) != record.get("sha256"):
            raise ValueError(f"manifest SHA-256 mismatch: {name}")
    if set(payloads) != expected_names:
        raise ValueError("ZIP contains unlisted or missing files")

    sums = _parse_sha256sums(payloads[SHA256SUMS_NAME])
    expected_sums = expected_names - {SHA256SUMS_NAME}
    if set(sums) != expected_sums:
        raise ValueError("SHA256SUMS path set mismatch")
    for name in expected_sums:
        if sha256_bytes(payloads[name]) != sums[name]:
            raise ValueError(f"SHA256SUMS mismatch: {name}")

    exit_code = manifest.get("exit_code")
    run_id = manifest.get("run_id")
    if not isinstance(exit_code, int):
        raise ValueError("manifest exit_code is invalid")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("manifest run_id is invalid")
    status = validate_run_evidence(payloads, exit_code=exit_code, run_id=run_id)
    if status != manifest.get("status"):
        raise ValueError("manifest status does not match embedded evidence")

    report: dict[str, Any] = {
        "schema_version": VERIFY_SCHEMA,
        "status": "PASS",
        "evidence_status": status,
        "run_id": run_id,
        "zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "manifest_sha256": manifest["manifest_sha256"],
        "verified_file_count": len(payloads),
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report
