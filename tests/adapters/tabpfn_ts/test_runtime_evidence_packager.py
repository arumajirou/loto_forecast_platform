from __future__ import annotations

import importlib.util
import json
import math
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


REPO_OVERLAY = Path(__file__).parents[3]
SCRIPT = REPO_OVERLAY / "scripts" / "package_tabpfn_ts_v2_runtime_evidence.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tabpfn_runtime_packager", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _build_run(tmp_path: Path, *, device: str = "cuda") -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    process_runs: list[dict[str, object]] = []
    evidence_files: list[Path] = []
    for index, pid in enumerate((101, 202), start=1):
        process_dir = run_dir / f"process-{index:02d}"
        process_dir.mkdir()
        for name, content in {
            "request.json": "{}\n",
            "response.json": "{}\n",
            "stdout.log": "stdout\n",
            "stderr.log": "",
        }.items():
            path = process_dir / name
            path.write_text(content, encoding="utf-8")
            evidence_files.append(path)
        process_runs.append(
            {
                "run_index": index,
                "process_pid": pid,
                "exit_code": 0,
                "started_at_utc": "2026-08-06T00:00:00+00:00",
                "finished_at_utc": "2026-08-06T00:00:01+00:00",
                "request_path": str(process_dir / "request.json"),
                "response_path": str(process_dir / "response.json"),
                "stdout_path": str(process_dir / "stdout.log"),
                "stderr_path": str(process_dir / "stderr.log"),
                "response_sha256": "a" * 64,
                "prediction_sha256": "b" * 64,
                "predictions": [float(value) for value in range(37)],
                "prediction_shape": [37],
                "requested_device": device,
                "execution_device": device,
                "cpu_fallback": False,
                "provider_gpu_pid": pid if device == "cuda" else None,
                "provider_peak_vram_bytes": 1024 if device == "cuda" else 0,
                "parameter_devices": ["cuda:0"] if device == "cuda" else ["cpu"],
                "external_gpu_samples": (
                    [
                        {
                            "pid": pid,
                            "gpu_uuid": "GPU-test",
                            "used_memory_bytes": 1024,
                            "observed_at_utc": "2026-08-06T00:00:00+00:00",
                        }
                    ]
                    if device == "cuda"
                    else []
                ),
                "pid_released_after_exit": True,
            }
        )
    report = {
        "schema_version": 1,
        "run_id": "test-run",
        "status": "PASS",
        "certification_class": "GPU_FORMAL" if device == "cuda" else "CPU_SMOKE",
        "created_at_utc": "2026-08-06T00:00:02+00:00",
        "checkpoint_evidence": {
            "snapshot_path": "/snapshot",
            "visible_checkpoint_path": "/snapshot/checkpoint",
            "resolved_checkpoint_path": "/blobs/checkpoint",
            "sha256": "c" * 64,
            "size_bytes": 1,
            "verified_before_load": True,
        },
        "process_runs": process_runs,
        "separate_process_reload": True,
        "deterministic_replay": True,
        "max_absolute_prediction_difference": 0.0,
        "prediction_locked_before_actuals": True,
        "failure_reason": None,
    }
    report_path = run_dir / "runtime-certification-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    evidence_files.append(report_path)
    (run_dir / "SHA256SUMS").write_text(
        "".join(f"{_sha256(path)}  {path.relative_to(run_dir)}\n" for path in evidence_files),
        encoding="utf-8",
    )
    return run_dir


def _build_host_inventory(tmp_path: Path, *, device: str = "cuda") -> Path:
    path = tmp_path / "host.json"
    path.write_text(
        json.dumps(
            {
                "git_head": "d" * 40,
                "request_sha256": "e" * 64,
                "pyproject_sha256": "f" * 64,
                "uv_lock_sha256": "1" * 64,
                "provider_environment": {
                    "tabpfn_time_series": "1.2.0",
                    "cuda_available": device == "cuda",
                },
                "nvidia_smi_gpus": ["GPU-test"] if device == "cuda" else [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_validate_runtime_report_rejects_cpu_fallback(tmp_path: Path) -> None:
    module = _load_module()
    report = json.loads(
        (_build_run(tmp_path) / "runtime-certification-report.json").read_text(encoding="utf-8")
    )
    report["process_runs"][0]["cpu_fallback"] = True
    with pytest.raises(module.EvidencePackagingError, match="CPU fallback"):
        module.validate_runtime_report(report, expected_device="cuda")


def test_validate_runtime_report_rejects_non_finite_predictions(tmp_path: Path) -> None:
    module = _load_module()
    report = json.loads(
        (_build_run(tmp_path) / "runtime-certification-report.json").read_text(encoding="utf-8")
    )
    report["process_runs"][0]["predictions"][0] = math.nan
    with pytest.raises(module.EvidencePackagingError, match="non-finite"):
        module.validate_runtime_report(report, expected_device="cuda")


def test_package_runtime_evidence_creates_verifiable_zip(tmp_path: Path) -> None:
    module = _load_module()
    run_dir = _build_run(tmp_path)
    host_inventory = _build_host_inventory(tmp_path)
    output_zip = tmp_path / "bundle.zip"
    zip_path, sha_path = module.package_runtime_evidence(
        run_dir=run_dir,
        output_zip=output_zip,
        expected_device="cuda",
        host_inventory_path=host_inventory,
    )
    assert zip_path.is_file()
    assert sha_path.is_file()
    assert _sha256(zip_path) in sha_path.read_text(encoding="utf-8")
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "README.md" in names
        assert "VERIFICATION_REPORT.md" in names
        assert "RUNBOOK.md" in names
        assert "ARTIFACT_MANIFEST.json" in names
        assert "SHA256SUMS" in names
        assert "runtime-evidence/runtime-certification-report.json" in names
        assert archive.testzip() is None


def test_package_runtime_evidence_rejects_tampered_run_file(tmp_path: Path) -> None:
    module = _load_module()
    run_dir = _build_run(tmp_path)
    (run_dir / "process-01" / "response.json").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(module.EvidencePackagingError, match="SHA256SUMS mismatch"):
        module.package_runtime_evidence(
            run_dir=run_dir,
            output_zip=tmp_path / "bundle.zip",
            expected_device="cuda",
        )


def test_package_runtime_evidence_rejects_untracked_run_file(tmp_path: Path) -> None:
    module = _load_module()
    run_dir = _build_run(tmp_path)
    (run_dir / "untracked.txt").write_text("not checksummed\n", encoding="utf-8")
    with pytest.raises(module.EvidencePackagingError, match="not covered by SHA256SUMS"):
        module.package_runtime_evidence(
            run_dir=run_dir,
            output_zip=tmp_path / "bundle.zip",
            expected_device="cuda",
        )


def test_target_host_wrapper_requires_explicit_license_acceptance(tmp_path: Path) -> None:
    import subprocess

    script = REPO_OVERLAY / "scripts" / "run_tabpfn_ts_v2_target_host_certification.sh"
    completed = subprocess.run(
        [
            "bash",
            str(script),
            "--repo-root",
            str(tmp_path),
            "--provider-python",
            str(tmp_path / "python"),
            "--request",
            str(tmp_path / "request.json"),
            "--snapshot",
            str(tmp_path / "snapshot"),
            "--repository-cache-root",
            str(tmp_path / "cache"),
            "--no-wait",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "--accept-prior-labs-license is required" in completed.stderr


def test_package_rejects_output_zip_inside_source_run(tmp_path: Path) -> None:
    module = _load_module()
    run_dir = _build_run(tmp_path)
    with pytest.raises(module.EvidencePackagingError, match="outside the source run"):
        module.package_runtime_evidence(
            run_dir=run_dir,
            output_zip=run_dir / "bundle.zip",
            expected_device="cuda",
            host_inventory_path=_build_host_inventory(tmp_path),
        )


def test_package_rejects_wrong_provider_package_version(tmp_path: Path) -> None:
    module = _load_module()
    run_dir = _build_run(tmp_path)
    inventory = _build_host_inventory(tmp_path)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["provider_environment"]["tabpfn_time_series"] = "0.0.0"
    inventory.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(module.EvidencePackagingError, match="package version"):
        module.package_runtime_evidence(
            run_dir=run_dir,
            output_zip=tmp_path / "bundle.zip",
            expected_device="cuda",
            host_inventory_path=inventory,
        )
