from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from loto.toto2_campaign.target_host_verify import verify_certification_archive

GAMES = ("numbers3", "numbers4", "miniloto", "loto6", "loto7")
CONTEXTS = (128, 256, 512)
HORIZONS = (1, 2, 5)
DEVICES = ("cpu", "cuda")


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True) + "\n").encode()


def _build_archive(path: Path, *, break_gpu: bool = False) -> str:
    files: dict[str, bytes] = {}
    cases = []
    for game in GAMES:
        for context in CONTEXTS:
            for horizon in HORIZONS:
                for device in DEVICES:
                    case_id = f"{game}-c{context}-h{horizon}-{device}"
                    cases.append(
                        {
                            "case_id": case_id,
                            "returncode": 0,
                            "response_status": "OK",
                        }
                    )
                    files[f"cases/{case_id}/response.json"] = _json_bytes(
                        {
                            "status": "OK",
                            "phase": "predict",
                            "effective_arguments": {"actuals_used": False},
                        }
                    )
                    files[f"cases/{case_id}/runtime/CERTIFICATION_RESULT.json"] = _json_bytes(
                        {
                            "status": "PASS",
                            "two_process_exact_replay": True,
                        }
                    )
                    files[f"cases/{case_id}/runtime/REPLAY_COMPARISON.json"] = _json_bytes(
                        {"exact_equal": True}
                    )
                    for process in ("process-1", "process-2"):
                        cuda = device == "cuda"
                        captured = cuda and not break_gpu
                        evidence = {
                            "requested_device": device,
                            "execution_device": "cuda:0" if cuda else "cpu",
                            "model_device": "cuda:0" if cuda else "cpu",
                            "output_device": "cuda:0" if cuda else "cpu",
                            "peak_vram_bytes": 1024 if cuda else 0,
                            "external_gpu_pid_captured": captured,
                            "cpu_fallback": False,
                            "runtime_scope": "FULL_INFERENCE",
                        }
                        prefix = f"cases/{case_id}/runtime/{process}"
                        files[f"{prefix}/runtime_evidence.json"] = _json_bytes(evidence)
                        if cuda:
                            files[f"{prefix}/external_gpu_pid_evidence.json"] = _json_bytes(
                                {
                                    "captured": captured,
                                    "gpu_uuids": ["GPU-test"] if captured else [],
                                }
                            )
    files["MATRIX_RESULT.json"] = _json_bytes(
        {
            "status": "PASS",
            "total_cases": 90,
            "passed_cases": 90,
            "runtime_certified": True,
            "forecast_accuracy_certified": False,
            "cases": cases,
        }
    )
    manifest_entries = [
        {
            "path": name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for name, data in sorted(files.items())
    ]
    files["ARTIFACT_MANIFEST.json"] = _json_bytes(
        {
            "schema_version": 1,
            "file_count": len(manifest_entries),
            "files": manifest_entries,
        }
    )
    files["SHA256SUMS"] = "".join(
        f"{entry['sha256']}  {entry['path']}\n" for entry in manifest_entries
    ).encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verify_complete_archive(tmp_path: Path) -> None:
    archive = tmp_path / "certification.zip"
    digest = _build_archive(archive)

    result = verify_certification_archive(archive, expected_sha256=digest)

    assert result["status"] == "VERIFIED"
    assert result["total_cases"] == 90
    assert result["gpu_processes_verified"] == 90
    assert result["forecast_accuracy_certified"] is False


def test_verify_rejects_missing_gpu_capture(tmp_path: Path) -> None:
    archive = tmp_path / "certification.zip"
    digest = _build_archive(archive, break_gpu=True)

    with pytest.raises(ValueError, match="GPU PID was not captured"):
        verify_certification_archive(archive, expected_sha256=digest)


def test_verify_rejects_archive_hash_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "certification.zip"
    _build_archive(archive)

    with pytest.raises(ValueError, match="archive SHA-256 mismatch"):
        verify_certification_archive(archive, expected_sha256="0" * 64)
