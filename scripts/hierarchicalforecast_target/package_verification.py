"""Independent verification of the sealed runtime ZIP and formal result."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .constants import (
    FORMAL_HORIZON,
    FORMAL_INSAMPLE_SIZE,
    FORMAL_SEED,
    FORMAL_TOLERANCE,
    GAMES,
    PACKAGE_MANIFEST,
    REQUIRED,
    TARGET_VERSION,
    CertificationError,
)
from .integrity import (
    canonical,
    compact_sha256,
    inside,
    load_json,
    require_directory,
    require_regular_file,
    safe_name,
    sha_file,
)
from .runtime_verification import verify_cases, verify_runtime_files


def verify_source_hashes(runtime: dict[str, object], repo_root: Path) -> None:
    source_hashes = runtime.get("source_sha256")
    if not isinstance(source_hashes, dict):
        raise CertificationError("runtime source-hash evidence is missing")
    expected = {
        "runtime_certification": sha_file(
            repo_root / "src/loto/reconciliation/runtime_certification.py"
        ),
        "hierarchy": sha_file(repo_root / "src/loto/reconciliation/hierarchy.py"),
    }
    if source_hashes != expected:
        raise CertificationError("runtime source-hash evidence mismatch")
    if runtime.get("code_sha256") != compact_sha256(expected):
        raise CertificationError("runtime code-set SHA-256 mismatch")


def verify_zip(zip_path: Path, run_id: str) -> dict[str, object]:
    require_regular_file(zip_path, "runtime ZIP")
    expected = {*(f"{run_id}/{name}" for name in REQUIRED), f"{run_id}/{PACKAGE_MANIFEST}"}
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != expected:
                raise CertificationError("ZIP coverage or duplicate-member failure")
            for info in infos:
                member = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if (
                    member.is_absolute()
                    or ".." in member.parts
                    or len(member.parts) != 2
                    or member.parts[0] != run_id
                    or info.is_dir()
                    or info.flag_bits & 1
                    or info.date_time != (1980, 1, 1, 0, 0, 0)
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.create_system != 3
                    or mode != 0o100644
                ):
                    raise CertificationError(f"invalid ZIP member: {info.filename}")
            if archive.testzip() is not None:
                raise CertificationError("ZIP CRC verification failed")
            manifest_bytes = archive.read(f"{run_id}/{PACKAGE_MANIFEST}")
            manifest = json.loads(manifest_bytes.decode())
            if not isinstance(manifest, dict) or manifest_bytes != canonical(manifest):
                raise CertificationError("package manifest is not canonical")
            if (
                manifest.get("run_id") != run_id
                or manifest.get("certification_status") != "VERIFIED"
            ):
                raise CertificationError("package manifest identity/status mismatch")
            rows = manifest.get("files")
            if not isinstance(rows, list) or len(rows) != len(REQUIRED):
                raise CertificationError("package manifest files must have exact coverage")
            observed: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise CertificationError("invalid package manifest row")
                name = safe_name(str(row.get("path", "")))
                if name in observed:
                    raise CertificationError(f"duplicate package manifest row: {name}")
                observed.add(name)
                data = archive.read(f"{run_id}/{name}")
                digest = hashlib.sha256(data).hexdigest()
                if row.get("bytes") != len(data) or row.get("sha256") != digest:
                    raise CertificationError(f"ZIP member evidence mismatch: {name}")
            if observed != set(REQUIRED):
                raise CertificationError("package manifest coverage mismatch")
            content_set = hashlib.sha256(canonical(rows)).hexdigest()
            if manifest.get("content_set_sha256") != content_set:
                raise CertificationError("package content-set hash mismatch")
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificationError(f"ZIP verification failed: {exc}") from exc
    return {
        "sha256": sha_file(zip_path),
        "bytes": zip_path.stat().st_size,
        "member_count": len(expected),
        "content_set_sha256": manifest["content_set_sha256"],
    }


def verify_formal(
    payload: dict[str, Any],
    output_root: Path,
    git_sha: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, object]:
    certification = payload.get("certification")
    package = payload.get("package")
    if not isinstance(certification, dict) or not isinstance(package, dict):
        raise CertificationError("CLI output lacks certification/package objects")
    _verify_summary_and_config(certification)
    runtime = _verify_dependency_and_runtime(certification, git_sha)
    if repo_root is not None:
        verify_source_hashes(runtime, repo_root)

    run_id = safe_name(str(certification.get("run_id", "")))
    raw_run_dir = Path(str(certification.get("run_directory", "")))
    if raw_run_dir.is_symlink():
        raise CertificationError("run directory must not be a symbolic link")
    run_dir = inside(raw_run_dir, output_root, "run directory")
    if run_dir.name != run_id:
        raise CertificationError("run directory and run_id mismatch")
    require_directory(run_dir, "runtime run directory")
    verify_runtime_files(run_dir, run_id)
    if load_json(run_dir / "RUNTIME_CERTIFICATION.json") != certification:
        raise CertificationError("persisted certification differs from CLI output")
    partition = verify_cases(
        run_dir,
        run_id,
        horizon=FORMAL_HORIZON,
        insample_size=FORMAL_INSAMPLE_SIZE,
        tolerance=FORMAL_TOLERANCE,
    )
    package_evidence = _verify_package_paths(package, output_root, run_dir, run_id)
    return {
        "run_id": run_id,
        "run_directory": str(run_dir),
        "summary": certification["summary"],
        "method_partition": partition,
        **package_evidence,
    }


def _verify_summary_and_config(certification: dict[str, object]) -> None:
    summary = certification.get("summary")
    expected_summary = {
        "expected_cases": 40,
        "executed_cases": 40,
        "passed_cases": 40,
        "failed_cases": 0,
        "exact_version_match": True,
        "module_distribution_version_consistent": True,
    }
    if (
        certification.get("status") != "VERIFIED"
        or certification.get("formal_success") is not True
        or not isinstance(summary, dict)
        or any(summary.get(key) != value for key, value in expected_summary.items())
    ):
        raise CertificationError("formal status or 40-case summary mismatch")
    config = certification.get("config")
    expected_config = {
        "games": list(GAMES),
        "seed": FORMAL_SEED,
        "horizon": FORMAL_HORIZON,
        "insample_size": FORMAL_INSAMPLE_SIZE,
        "coherence_tolerance": FORMAL_TOLERANCE,
        "expected_version": TARGET_VERSION,
    }
    if not isinstance(config, dict) or any(config.get(k) != v for k, v in expected_config.items()):
        raise CertificationError("formal configuration evidence mismatch")


def _verify_dependency_and_runtime(
    certification: dict[str, object], git_sha: str
) -> dict[str, object]:
    dependency = certification.get("dependency")
    runtime = certification.get("runtime")
    if (
        not isinstance(dependency, dict)
        or dependency.get("import_status") != "PASS"
        or dependency.get("installed_version") != TARGET_VERSION
        or dependency.get("distribution_version") != TARGET_VERSION
        or dependency.get("version_consistent") is not True
    ):
        raise CertificationError("runtime dependency evidence mismatch")
    if (
        not isinstance(runtime, dict)
        or runtime.get("git_commit") != git_sha
        or runtime.get("device") != "cpu"
        or runtime.get("gpu_expected") is not False
        or not isinstance(runtime.get("packages"), dict)
        or runtime["packages"].get("hierarchicalforecast") != TARGET_VERSION
    ):
        raise CertificationError("runtime environment/git evidence mismatch")
    return runtime


def _verify_package_paths(
    package: dict[str, object],
    output_root: Path,
    run_dir: Path,
    run_id: str,
) -> dict[str, object]:
    raw_zip = Path(str(package.get("path", "")))
    raw_sidecar = Path(str(package.get("sha256_sidecar", "")))
    if raw_zip.is_symlink() or raw_sidecar.is_symlink():
        raise CertificationError("package ZIP and sidecar must not be symbolic links")
    zip_path = inside(raw_zip, output_root, "ZIP")
    sidecar = inside(raw_sidecar, output_root, "sidecar")
    require_regular_file(zip_path, "runtime ZIP")
    require_regular_file(sidecar, "runtime ZIP sidecar")
    if zip_path != run_dir.with_suffix(".zip") or sidecar != Path(f"{zip_path}.sha256"):
        raise CertificationError("package path relationship mismatch")
    digest = sha_file(zip_path)
    if sidecar.read_text(encoding="utf-8") != f"{digest}  {zip_path.name}\n":
        raise CertificationError("ZIP sidecar mismatch")
    zip_result = verify_zip(zip_path, run_id)
    expected = {
        "status": "VERIFIED",
        "run_id": run_id,
        "certification_status": "VERIFIED",
        "sha256": digest,
        "bytes": zip_result["bytes"],
        "member_count": zip_result["member_count"],
        "content_set_sha256": zip_result["content_set_sha256"],
    }
    if any(package.get(key) != value for key, value in expected.items()):
        raise CertificationError("CLI package evidence mismatch")
    return {
        "zip_path": str(zip_path),
        "zip_sha256": digest,
        "zip_sidecar": str(sidecar),
        "zip_member_count": zip_result["member_count"],
        "zip_bytes": zip_result["bytes"],
    }
