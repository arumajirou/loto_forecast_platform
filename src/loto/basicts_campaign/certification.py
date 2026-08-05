from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

EXPECTED_BASICTS_VERSION = "1.1.0"
EXPECTED_UPSTREAM_REVISION = "c2bb6e31e591167e84459775a21a62e70a5893ce"
SHA256_LINE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$")


class CertificationError(RuntimeError):
    """Raised when P0 evidence is incomplete, unsafe, or internally inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificationError(f"cannot read JSON evidence: {path}") from exc
    if not isinstance(payload, dict):
        raise CertificationError(f"JSON evidence must contain an object: {path}")
    return payload


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


def _regular_files(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise CertificationError(f"evidence directory does not exist: {directory}")
    files: dict[str, Path] = {}
    for path in directory.iterdir():
        if path.is_symlink():
            raise CertificationError(f"symbolic links are forbidden in evidence: {path}")
        if path.is_file():
            files[path.name] = path
    return files


def verify_sha256sums(directory: Path) -> dict[str, str]:
    """Verify a portable SHA256SUMS file without accepting paths or duplicate entries."""

    files = _regular_files(directory)
    sums_path = files.get("SHA256SUMS")
    if sums_path is None:
        raise CertificationError(f"SHA256SUMS is missing: {directory}")

    expected: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        sums_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        match = SHA256_LINE.fullmatch(raw_line)
        if match is None:
            raise CertificationError(f"invalid SHA256SUMS line {line_number}: {raw_line!r}")
        name = match.group("name")
        if name == "SHA256SUMS":
            raise CertificationError("SHA256SUMS must not hash itself")
        if name in expected:
            raise CertificationError(f"duplicate SHA256SUMS entry: {name}")
        expected[name] = match.group("digest")

    actual_names = set(files) - {"SHA256SUMS"}
    if set(expected) != actual_names:
        missing = sorted(actual_names - set(expected))
        unknown = sorted(set(expected) - actual_names)
        raise CertificationError(
            f"SHA256SUMS file set mismatch: missing={missing}, unknown={unknown}"
        )
    for name, digest in expected.items():
        actual = _sha256(files[name])
        if actual != digest:
            raise CertificationError(
                f"SHA-256 mismatch for {directory / name}: expected {digest}, got {actual}"
            )
    return expected


def _verify_manifest(directory: Path, operation: str) -> dict[str, Any]:
    files = _regular_files(directory)
    manifest_path = files.get("ARTIFACT_MANIFEST.json")
    if manifest_path is None:
        raise CertificationError(f"ARTIFACT_MANIFEST.json is missing: {directory}")
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != "1.0":
        raise CertificationError("unsupported artifact manifest schema")
    if manifest.get("status") != "PASS":
        raise CertificationError("artifact manifest status is not PASS")
    if manifest.get("operation") != operation:
        raise CertificationError("artifact manifest operation mismatch")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise CertificationError("artifact manifest files must be a list")
    manifest_names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise CertificationError("artifact manifest entry must be an object")
        name = entry.get("path")
        if not isinstance(name, str) or SHA256_LINE.fullmatch(f"{'0' * 64}  {name}") is None:
            raise CertificationError(f"unsafe artifact manifest path: {name!r}")
        if name in manifest_names:
            raise CertificationError(f"duplicate artifact manifest path: {name}")
        manifest_names.add(name)
        path = files.get(name)
        if path is None:
            raise CertificationError(f"manifest artifact is missing: {name}")
        if entry.get("size_bytes") != path.stat().st_size:
            raise CertificationError(f"manifest size mismatch: {name}")
        if entry.get("sha256") != _sha256(path):
            raise CertificationError(f"manifest SHA-256 mismatch: {name}")

    expected_names = set(files) - {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    if manifest_names != expected_names:
        raise CertificationError(
            "artifact manifest file set mismatch: "
            f"expected={sorted(expected_names)}, actual={sorted(manifest_names)}"
        )
    return manifest


def _verify_response(directory: Path, operation: str) -> dict[str, Any]:
    response = _load_json(directory / "response.json")
    required = {
        "status": "PASS",
        "operation": operation,
        "provider": "basicts",
        "environment_lane": "basicts-py311",
        "expected_basicts_version": EXPECTED_BASICTS_VERSION,
        "actual_basicts_version": EXPECTED_BASICTS_VERSION,
        "expected_upstream_revision": EXPECTED_UPSTREAM_REVISION,
        "actual_upstream_revision": EXPECTED_UPSTREAM_REVISION,
    }
    for field, expected in required.items():
        if response.get(field) != expected:
            raise CertificationError(
                f"response field mismatch for {operation}.{field}: "
                f"expected {expected!r}, got {response.get(field)!r}"
            )
    if response.get("error") is not None:
        raise CertificationError(f"PASS response contains an error for {operation}")
    evidence = response.get("evidence")
    if not isinstance(evidence, dict):
        raise CertificationError(f"response evidence must be an object for {operation}")
    return response


def verify_provider_bundle(directory: Path, operation: str) -> dict[str, Any]:
    """Verify one provider response bundle and operation-specific PASS evidence."""

    digests = verify_sha256sums(directory)
    manifest = _verify_manifest(directory, operation)
    response = _verify_response(directory, operation)
    evidence = response["evidence"]

    if operation == "identity":
        if evidence.get("identity_status") != "PASS":
            raise CertificationError("identity operation did not record PASS")
        if evidence.get("python_process_boundary") is not True:
            raise CertificationError("identity process boundary was not verified")
    elif operation == "validate_config":
        if evidence.get("config_import_policy") != "ALLOWLIST":
            raise CertificationError("config import policy is not ALLOWLIST")
        count = evidence.get("resolved_count")
        resolved = evidence.get("resolved")
        if not isinstance(count, int) or count < 1:
            raise CertificationError("validate_config resolved_count must be positive")
        if not isinstance(resolved, list) or len(resolved) != count:
            raise CertificationError("validate_config resolved evidence is inconsistent")
    elif operation == "dlinear_smoke":
        required = {
            "model_name": "DLinear",
            "device": "cpu",
            "cpu_fallback": False,
            "prediction_finite": True,
            "state_dict_finite": True,
            "save_load_exact_match": True,
        }
        for field, expected in required.items():
            if evidence.get(field) != expected:
                raise CertificationError(
                    f"DLinear evidence mismatch for {field}: "
                    f"expected {expected!r}, got {evidence.get(field)!r}"
                )
        shape = evidence.get("prediction_shape")
        if not isinstance(shape, list) or len(shape) != 3 or not all(
            isinstance(value, int) and value > 0 for value in shape
        ):
            raise CertificationError("DLinear prediction shape is invalid")
    else:
        raise CertificationError(f"unsupported P0 operation: {operation}")

    return {
        "operation": operation,
        "directory": str(directory),
        "response_sha256": digests["response.json"],
        "manifest_sha256": _sha256(directory / "ARTIFACT_MANIFEST.json"),
        "file_count": len(manifest["files"]),
    }


def verify_lockfile(lockfile: Path) -> dict[str, Any]:
    """Require a non-empty uv lock containing the frozen BasicTS revision."""

    if lockfile.is_symlink() or not lockfile.is_file() or lockfile.stat().st_size <= 0:
        raise CertificationError(f"reviewed uv.lock is missing or invalid: {lockfile}")
    text = lockfile.read_text(encoding="utf-8")
    lowered = text.lower()
    if "basicts" not in lowered:
        raise CertificationError("uv.lock does not contain a BasicTS package record")
    if EXPECTED_UPSTREAM_REVISION not in text:
        raise CertificationError("uv.lock does not contain the frozen BasicTS revision")
    return {
        "path": str(lockfile),
        "size_bytes": lockfile.stat().st_size,
        "sha256": _sha256(lockfile),
        "frozen_revision": EXPECTED_UPSTREAM_REVISION,
    }


def certify_p0(
    *,
    lockfile: Path,
    identity_dir: Path,
    config_dir: Path,
    dlinear_dir: Path,
) -> dict[str, Any]:
    """Build a fail-closed P0 certificate from independently hashed evidence."""

    return {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "BASICTS_P0_IDENTITY_CONFIG_DLINEAR_CPU",
        "basicts_version": EXPECTED_BASICTS_VERSION,
        "upstream_revision": EXPECTED_UPSTREAM_REVISION,
        "lockfile": verify_lockfile(lockfile),
        "bundles": [
            verify_provider_bundle(identity_dir, "identity"),
            verify_provider_bundle(config_dir, "validate_config"),
            verify_provider_bundle(dlinear_dir, "dlinear_smoke"),
        ],
        "certified": {
            "isolated_python_lane": "3.11",
            "identity": True,
            "config_import_allowlist": True,
            "dlinear_cpu_fit_predict": True,
            "save_load_repredict_exact": True,
            "portable_sha256": True,
        },
        "not_certified": [
            "BasicTS Launcher or Runner",
            "GPU, AMP, DDP, or distributed execution",
            "chronological CV, OOF, HPO, Holdout, or Prospective evaluation",
            "accuracy improvement or baseline superiority",
            "shared worker, catalog, CLI, MLflow, or PostgreSQL integration",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BasicTS P0 evidence")
    parser.add_argument("--lockfile", type=Path, required=True)
    parser.add_argument("--identity-dir", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--dlinear-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = certify_p0(
        lockfile=args.lockfile,
        identity_dir=args.identity_dir,
        config_dir=args.config_dir,
        dlinear_dir=args.dlinear_dir,
    )
    report_path = args.output_dir / "P0_CERTIFICATION_REPORT.json"
    _atomic_write_text(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    checksum_path = args.output_dir / "P0_CERTIFICATION_REPORT.json.sha256"
    _atomic_write_text(checksum_path, f"{_sha256(report_path)}  {report_path.name}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
