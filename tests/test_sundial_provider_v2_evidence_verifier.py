from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    path = ROOT / "scripts" / "verify_sundial_provider_v2_evidence.py"
    spec = importlib.util.spec_from_file_location("sundial_evidence_verifier", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFIER = _load()


def _response(num_samples: int, device: str, pid: int) -> dict[str, Any]:
    samples = [[[float(series + sample)] for sample in range(num_samples)] for series in range(7)]
    return {
        "status": "OK",
        "provider_version": 2,
        "repo_id": VERIFIER.REPO_ID,
        "revision": VERIFIER.REVISION,
        "samples_shape": [7, num_samples, 1],
        "samples": samples,
        "predictions": [float(index) for index in range(7)],
        "gpu_evidence": {
            "execution_device": device,
            "gpu_used": device == "cuda",
            "gpu_pid": pid if device == "cuda" else None,
            "peak_vram_bytes": 1024 if device == "cuda" else 0,
            "cpu_fallback": False,
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _build_run(tmp_path: Path) -> Path:
    run_id = "sundial-v2-20260806-010203"
    run_dir = tmp_path / run_id
    seed = 42
    cases = []
    for index, name in enumerate(VERIFIER.EXPECTED_CASES, start=100):
        device = "cpu" if name == "cpu-smoke-ns001" else "cuda"
        if name == "cpu-smoke-ns001" or name == "cuda-ns001":
            count = 1
        elif name == "cuda-ns003":
            count = 3
        elif name in {"cuda-ns020", "cuda-replay-a", "cuda-replay-b"}:
            count = 20
        elif name == "cuda-ns050":
            count = 50
        else:
            count = 100
        case_dir = run_dir / "cases" / name
        request = {
            "repo_id": VERIFIER.REPO_ID,
            "revision": VERIFIER.REVISION,
            "device": device,
            "num_samples": count,
            "prediction_length": 1,
            "local_files_only": True,
            "seed": seed,
        }
        response = _response(count, device, index)
        monitor = {
            "pid": index,
            "external_seen": device == "cuda",
            "external_peak_mib": 512 if device == "cuda" else 0,
        }
        _write_json(case_dir / "request.json", request)
        _write_json(case_dir / "response.json", response)
        _write_json(case_dir / "gpu-monitor.json", monitor)
        (case_dir / "stdout.log").write_text("", encoding="utf-8")
        (case_dir / "stderr.log").write_text("", encoding="utf-8")
        cases.append(
            {
                "name": name,
                "device": device,
                "num_samples": count,
                "seed": seed,
                "passed": True,
                "reasons": [],
                "return_code": 0,
                "timed_out": False,
                "pid": index,
                "external_gpu_pid_seen": device == "cuda",
                "external_peak_vram_mib": 512 if device == "cuda" else 0,
                "request_sha256": VERIFIER.sha256(case_dir / "request.json"),
                "response_sha256": VERIFIER.sha256(case_dir / "response.json"),
            }
        )
    replay = VERIFIER.compare_samples(
        VERIFIER.load_json(run_dir / "cases/cuda-replay-a/response.json"),
        VERIFIER.load_json(run_dir / "cases/cuda-replay-b/response.json"),
    )
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "PASS",
        "repo_id": VERIFIER.REPO_ID,
        "revision": VERIFIER.REVISION,
        "sample_counts": list(VERIFIER.EXPECTED_SAMPLE_COUNTS),
        "seed": seed,
        "cases": cases,
        "formal_gpu_certification": True,
        "cpu_fallback_allowed": False,
    }
    _write_json(run_dir / "certification-summary.json", summary)
    _write_json(run_dir / "reproducibility.json", replay)
    _write_json(
        run_dir / "environment.json",
        {
            "run_id": run_id,
            "git_commit": "abc",
            "git_branch": "feat/sundial-probabilistic-provider-v2",
            "git_status_porcelain": "",
        },
    )
    _write_json(
        run_dir / "ARTIFACT_MANIFEST.json",
        {
            "run_id": run_id,
            "status": "PASS",
            "case_directories": list(VERIFIER.EXPECTED_CASES),
            "required_files": [
                "environment.json",
                "certification-summary.json",
                "reproducibility.json",
                "SHA256SUMS",
            ],
        },
    )
    (run_dir / "status.txt").write_text(
        f"SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS\nRUN_DIR={run_dir}\n",
        encoding="utf-8",
    )
    files = sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    (run_dir / "SHA256SUMS").write_text(
        "\n".join(f"{VERIFIER.sha256(path)}  {path.relative_to(run_dir)}" for path in files) + "\n",
        encoding="utf-8",
    )
    return run_dir


def test_valid_run_passes(tmp_path: Path) -> None:
    report = VERIFIER.verify_run(
        _build_run(tmp_path),
        repo_root=None,
        expected_commit="abc",
        expected_branch="feat/sundial-probabilistic-provider-v2",
    )
    assert report["status"] == "PASS"
    assert report["reasons"] == []


def test_checksum_tampering_is_blocked(tmp_path: Path) -> None:
    run_dir = _build_run(tmp_path)
    (run_dir / "status.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(VERIFIER.EvidenceError, match="SHA-256 mismatch"):
        VERIFIER.verify_run(run_dir, repo_root=None, expected_commit=None, expected_branch=None)


def test_cpu_fallback_fails_verification(tmp_path: Path) -> None:
    run_dir = _build_run(tmp_path)
    response_path = run_dir / "cases/cuda-ns003/response.json"
    response = VERIFIER.load_json(response_path)
    response["gpu_evidence"]["cpu_fallback"] = True
    _write_json(response_path, response)
    files = sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    (run_dir / "SHA256SUMS").write_text(
        "\n".join(f"{VERIFIER.sha256(path)}  {path.relative_to(run_dir)}" for path in files) + "\n",
        encoding="utf-8",
    )
    report = VERIFIER.verify_run(
        run_dir,
        repo_root=None,
        expected_commit=None,
        expected_branch=None,
    )
    assert report["status"] == "FAIL"
    assert any("CPU_FALLBACK" in reason for reason in report["reasons"])


def test_archive_contains_run_and_verification(tmp_path: Path) -> None:
    run_dir = _build_run(tmp_path)
    verification = tmp_path / "verified"
    verification.mkdir()
    (verification / "VERIFICATION_REPORT.md").write_text("PASS\n", encoding="utf-8")
    archive = tmp_path / "evidence.zip"
    VERIFIER.create_archive(run_dir, verification, archive)
    assert archive.is_file()
    assert archive.with_suffix(".zip.sha256").is_file()
