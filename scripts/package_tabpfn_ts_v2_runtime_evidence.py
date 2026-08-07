from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EvidencePackagingError(RuntimeError):
    """Raised when runtime evidence is incomplete or internally inconsistent."""


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidencePackagingError(f"expected JSON object: {path}")
    return payload


def _require_hash(value: object, *, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise EvidencePackagingError(f"{label} is not a lowercase SHA-256")
    return text


def validate_runtime_report(
    report: Mapping[str, Any],
    *,
    expected_device: str,
) -> None:
    expected_class = "GPU_FORMAL" if expected_device == "cuda" else "CPU_SMOKE"
    if report.get("status") != "PASS":
        raise EvidencePackagingError("runtime report status is not PASS")
    if report.get("certification_class") != expected_class:
        raise EvidencePackagingError(
            "runtime certification class does not match expected device: "
            f"expected={expected_class}, actual={report.get('certification_class')}"
        )
    if report.get("separate_process_reload") is not True:
        raise EvidencePackagingError("separate-process reload is not certified")
    if report.get("deterministic_replay") is not True:
        raise EvidencePackagingError("deterministic replay is not certified")
    if report.get("prediction_locked_before_actuals") is not True:
        raise EvidencePackagingError("prediction was not locked before actuals")

    checkpoint = report.get("checkpoint_evidence")
    if not isinstance(checkpoint, Mapping):
        raise EvidencePackagingError("checkpoint evidence is missing")
    if checkpoint.get("verified_before_load") is not True:
        raise EvidencePackagingError("checkpoint was not verified before load")
    _require_hash(checkpoint.get("sha256"), label="checkpoint sha256")

    process_runs = report.get("process_runs")
    if not isinstance(process_runs, list) or len(process_runs) < 2:
        raise EvidencePackagingError("at least two process runs are required")
    pids: set[int] = set()
    prediction_hashes: set[str] = set()
    for index, run in enumerate(process_runs, start=1):
        if not isinstance(run, Mapping):
            raise EvidencePackagingError(f"process run {index} is not an object")
        pid = int(run.get("process_pid", 0))
        if pid <= 0 or pid in pids:
            raise EvidencePackagingError("provider process PIDs must be positive and distinct")
        pids.add(pid)
        if int(run.get("exit_code", -1)) != 0:
            raise EvidencePackagingError(f"provider process {pid} did not exit successfully")
        predictions = run.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != 37:
            raise EvidencePackagingError(f"provider process {pid} output shape is not [37]")
        if not all(math.isfinite(float(value)) for value in predictions):
            raise EvidencePackagingError(f"provider process {pid} contains non-finite values")
        if run.get("prediction_shape") != [37]:
            raise EvidencePackagingError(f"provider process {pid} declared an invalid shape")
        if run.get("requested_device") != expected_device:
            raise EvidencePackagingError(f"provider process {pid} requested-device mismatch")
        if run.get("execution_device") != expected_device:
            raise EvidencePackagingError(f"provider process {pid} execution-device mismatch")
        if run.get("cpu_fallback") is not False:
            raise EvidencePackagingError(f"provider process {pid} used CPU fallback")
        if run.get("pid_released_after_exit") is not True:
            raise EvidencePackagingError(f"provider process {pid} GPU PID was not released")
        prediction_hashes.add(
            _require_hash(run.get("prediction_sha256"), label=f"process {pid} prediction sha256")
        )
        _require_hash(run.get("response_sha256"), label=f"process {pid} response sha256")

        if expected_device == "cuda":
            if int(run.get("provider_gpu_pid", 0)) != pid:
                raise EvidencePackagingError(f"provider process {pid} GPU PID mismatch")
            if int(run.get("provider_peak_vram_bytes", 0)) <= 0:
                raise EvidencePackagingError(f"provider process {pid} has no positive peak VRAM")
            parameter_devices = run.get("parameter_devices")
            if not isinstance(parameter_devices, list) or not any(
                str(device).startswith("cuda") for device in parameter_devices
            ):
                raise EvidencePackagingError(f"provider process {pid} lacks CUDA parameters")
            samples = run.get("external_gpu_samples")
            if not isinstance(samples, list) or not samples:
                raise EvidencePackagingError(f"provider process {pid} lacks external GPU samples")
            matching = [sample for sample in samples if int(sample.get("pid", 0)) == pid]
            if not matching:
                raise EvidencePackagingError(f"provider process {pid} was not observed externally")
            if max(int(sample.get("used_memory_bytes", 0)) for sample in matching) <= 0:
                raise EvidencePackagingError(
                    f"provider process {pid} external VRAM is not positive"
                )
            if any(not str(sample.get("gpu_uuid", "")) for sample in matching):
                raise EvidencePackagingError(f"provider process {pid} GPU UUID is missing")
        elif run.get("provider_gpu_pid") is not None:
            raise EvidencePackagingError("CPU smoke must not report a provider GPU PID")

    if len(prediction_hashes) != 1:
        raise EvidencePackagingError("separate-process prediction SHA-256 values differ")


def validate_host_inventory(
    inventory: Mapping[str, Any],
    *,
    expected_device: str,
) -> None:
    git_head = str(inventory.get("git_head", ""))
    if len(git_head) != 40 or any(character not in "0123456789abcdef" for character in git_head):
        raise EvidencePackagingError("host inventory Git HEAD is not a full commit SHA")
    for field in ("request_sha256", "pyproject_sha256", "uv_lock_sha256"):
        _require_hash(inventory.get(field), label=f"host inventory {field}")
    provider = inventory.get("provider_environment")
    if not isinstance(provider, Mapping):
        raise EvidencePackagingError("host inventory provider environment is missing")
    if provider.get("tabpfn_time_series") != "1.2.0":
        raise EvidencePackagingError("provider package version is not tabpfn-time-series==1.2.0")
    if expected_device == "cuda":
        if provider.get("cuda_available") is not True:
            raise EvidencePackagingError("provider environment did not report CUDA available")
        gpus = inventory.get("nvidia_smi_gpus")
        if not isinstance(gpus, list) or not gpus:
            raise EvidencePackagingError("host inventory contains no nvidia-smi GPU record")


def parse_sha256sums(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            digest, relative = raw_line.split("  ", 1)
        except ValueError as exc:
            raise EvidencePackagingError(
                f"invalid SHA256SUMS line {line_number}: {raw_line}"
            ) from exc
        entries.append((_require_hash(digest, label="SHA256SUMS digest"), relative))
    if not entries:
        raise EvidencePackagingError("SHA256SUMS is empty")
    return entries


def verify_run_sha256sums(run_dir: Path) -> list[Path]:
    checksum_path = run_dir / "SHA256SUMS"
    if not checksum_path.is_file():
        raise EvidencePackagingError("run SHA256SUMS is missing")
    verified: list[Path] = [checksum_path]
    for expected, relative in parse_sha256sums(checksum_path):
        candidate = (run_dir / relative).resolve()
        try:
            candidate.relative_to(run_dir.resolve())
        except ValueError as exc:
            raise EvidencePackagingError(
                f"SHA256SUMS path escapes run directory: {relative}"
            ) from exc
        if not candidate.is_file():
            raise EvidencePackagingError(f"SHA256SUMS file is missing: {relative}")
        actual = sha256_path(candidate)
        if actual != expected:
            raise EvidencePackagingError(
                f"SHA256SUMS mismatch for {relative}: expected={expected}, actual={actual}"
            )
        verified.append(candidate)
    actual_files = {path.resolve() for path in run_dir.rglob("*") if path.is_file()}
    verified_files = {path.resolve() for path in verified}
    unexpected = sorted(actual_files - verified_files)
    if unexpected:
        relative_paths = ", ".join(str(path.relative_to(run_dir)) for path in unexpected)
        raise EvidencePackagingError(
            f"run directory contains files not covered by SHA256SUMS: {relative_paths}"
        )
    return verified


def _manifest_entries(root: Path, files: Iterable[Path]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(set(files)):
        entries.append(
            {
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            }
        )
    return entries


def _write_support_documents(
    package_root: Path,
    *,
    report: Mapping[str, Any],
    source_run_dir: Path,
    host_inventory: Mapping[str, Any] | None,
) -> list[Path]:
    created_at = datetime.now(UTC).isoformat()
    run_id = str(report.get("run_id"))
    certification_class = str(report.get("certification_class"))
    readme = package_root / "README.md"
    verification = package_root / "VERIFICATION_REPORT.md"
    runbook = package_root / "RUNBOOK.md"
    inventory_path = package_root / "host-inventory.json"

    readme.write_text(
        "# TabPFN-TS V2 Runtime Evidence Bundle\n\n"
        f"Run ID: `{run_id}`  \n"
        f"Certification class: `{certification_class}`  \n"
        f"Created at: `{created_at}`\n\n"
        "This bundle contains immutable runtime evidence copied from the certifier run. "
        "The package does not establish forecasting accuracy or production eligibility.\n",
        encoding="utf-8",
    )
    verification.write_text(
        "# Verification Report\n\n"
        "Status: `VERIFIED_RUNTIME_EVIDENCE_PACKAGE`\n\n"
        f"- Source run directory: `{source_run_dir}`\n"
        f"- Runtime status: `{report.get('status')}`\n"
        f"- Certification class: `{certification_class}`\n"
        f"- Separate-process reload: `{report.get('separate_process_reload')}`\n"
        f"- Deterministic replay: `{report.get('deterministic_replay')}`\n"
        f"- Prediction locked before actuals: `{report.get('prediction_locked_before_actuals')}`\n"
        "- Maximum absolute replay difference: "
        f"`{report.get('max_absolute_prediction_difference')}`\n\n"
        "The source run SHA256SUMS was verified before packaging. The package-level "
        "ARTIFACT_MANIFEST.json and SHA256SUMS cover every payload file.\n",
        encoding="utf-8",
    )
    runbook.write_text(
        "# Runbook\n\n"
        "1. Verify the ZIP SHA-256 using the adjacent `.sha256` file.\n"
        "2. Extract the ZIP without changing file contents.\n"
        "3. Run `sha256sum -c SHA256SUMS` from the extracted package root.\n"
        "4. Review `VERIFICATION_REPORT.md` and "
        "`runtime-evidence/runtime-certification-report.json`.\n"
        "5. Do not interpret this artifact as an accuracy or champion-model result.\n",
        encoding="utf-8",
    )
    inventory_path.write_text(
        json.dumps(dict(host_inventory or {}), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return [readme, verification, runbook, inventory_path]


def package_runtime_evidence(
    *,
    run_dir: Path,
    output_zip: Path,
    expected_device: str,
    host_inventory_path: Path | None = None,
) -> tuple[Path, Path]:
    run_dir = run_dir.resolve()
    report_path = run_dir / "runtime-certification-report.json"
    if not report_path.is_file():
        raise EvidencePackagingError("runtime-certification-report.json is missing")
    report = load_json_object(report_path)
    validate_runtime_report(report, expected_device=expected_device)
    verified_run_files = verify_run_sha256sums(run_dir)
    if host_inventory_path is None:
        raise EvidencePackagingError("host inventory is required for formal packaging")
    host_inventory = load_json_object(host_inventory_path.resolve())
    validate_host_inventory(host_inventory, expected_device=expected_device)

    output_zip = output_zip.resolve()
    try:
        output_zip.relative_to(run_dir)
    except ValueError:
        pass
    else:
        raise EvidencePackagingError("output ZIP must be outside the source run directory")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tabpfn-v2-runtime-evidence-") as temporary:
        package_root = Path(temporary) / "tabpfn-ts-v2-runtime-evidence"
        evidence_root = package_root / "runtime-evidence"
        shutil.copytree(run_dir, evidence_root, symlinks=False)
        support_files = _write_support_documents(
            package_root,
            report=report,
            source_run_dir=run_dir,
            host_inventory=host_inventory,
        )
        copied_run_files = [
            evidence_root / path.relative_to(run_dir) for path in verified_run_files
        ]
        manifest_path = package_root / "ARTIFACT_MANIFEST.json"
        package_files_before_manifest = [*support_files, *copied_run_files]
        manifest_payload = {
            "schema_version": 1,
            "run_id": report.get("run_id"),
            "certification_class": report.get("certification_class"),
            "created_at_utc": datetime.now(UTC).isoformat(),
            "files": _manifest_entries(package_root, package_files_before_manifest),
        }
        manifest_path.write_text(
            json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        all_files = [*package_files_before_manifest, manifest_path]
        checksums_path = package_root / "SHA256SUMS"
        checksums_path.write_text(
            "".join(
                f"{sha256_path(path)}  {path.relative_to(package_root)}\n"
                for path in sorted(all_files)
            ),
            encoding="utf-8",
        )

        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package_root))

    sha_path = output_zip.with_suffix(output_zip.suffix + ".sha256")
    sha_path.write_text(f"{sha256_path(output_zip)}  {output_zip.name}\n", encoding="utf-8")
    return output_zip, sha_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Package verified TabPFN-TS V2 runtime evidence")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-zip", required=True, type=Path)
    parser.add_argument("--expected-device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--host-inventory", required=True, type=Path)
    args = parser.parse_args()
    try:
        output_zip, sha_path = package_runtime_evidence(
            run_dir=args.run_dir,
            output_zip=args.output_zip,
            expected_device=args.expected_device,
            host_inventory_path=args.host_inventory,
        )
    except Exception as exc:
        print(f"PACKAGE_STATUS=FAIL\nERROR_TYPE={type(exc).__name__}\nMESSAGE={exc}")
        return 2
    print(f"PACKAGE_STATUS=PASS\nZIP={output_zip}\nZIP_SHA256_FILE={sha_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
