from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loto.adapters.timesfm25.contracts import TimesFM25Request
from loto.timesfm25_campaign.model_manifest import (
    BackendManifest,
    ModelManifest,
    PackageProvenance,
)
from loto.timesfm25_campaign.preflight import offline_environment, run_preflight


def _request(snapshot: Path) -> TimesFM25Request:
    return TimesFM25Request.model_validate(
        {
            "run_id": "preflight-test",
            "backend": "pytorch_native",
            "repo_id": "google/timesfm-2.5-200m-pytorch",
            "revision": "1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
            "game_geometry": {
                "game_id": "test",
                "position_count": 3,
                "candidate_min": 0,
                "candidate_max": 9,
            },
            "series_ids": ["n1", "n2", "n3"],
            "history": {
                "n1": [1, 2, 3, 4],
                "n2": [2, 3, 4, 5],
                "n3": [3, 4, 5, 6],
            },
            "context_length": 4,
            "prediction_length": 1,
            "device": "cuda",
            "snapshot_path": str(snapshot.resolve()),
        }
    )


def _manifest(weight_hash: str) -> ModelManifest:
    backend = BackendManifest(
        backend="pytorch_native",
        repo_id="google/timesfm-2.5-200m-pytorch",
        revision="1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
        weight_sha256=weight_hash,
        environment="environments/timesfm25-pytorch",
        runtime_status="IMPLEMENTED_NOT_GPU_CERTIFIED",
    )
    return ModelManifest(
        base_model_id="timesfm-2.5-200m",
        algorithm_identity="timesfm-2.5-200m",
        package_provenance=PackageProvenance(
            package="timesfm",
            version="2.0.2",
            wheel_sha256="a" * 64,
            sdist_sha256="b" * 64,
            source_revision="c" * 40,
        ),
        backends={"pytorch_native": backend},
    )


def _environment(tmp_path: Path) -> Path:
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "pyproject.toml").write_text(
        """[project]
name = "test"
version = "0.1.0"
dependencies = [
  "timesfm[torch]==2.0.2",
  "torch==2.9.1",
  "huggingface-hub==0.36.2",
]
""",
        encoding="utf-8",
    )
    (environment / "uv.lock").write_text(
        """version = 1
[[package]]
name = "timesfm"
version = "2.0.2"
[[package]]
name = "torch"
version = "2.9.1"
[[package]]
name = "huggingface-hub"
version = "0.36.2"
""",
        encoding="utf-8",
    )
    return environment


def _snapshot(tmp_path: Path, *, extra_weight: bool = False) -> tuple[Path, str]:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "config.json").write_text('{"model_type":"timesfm"}\n', encoding="utf-8")
    weight = snapshot / "model.safetensors"
    weight.write_bytes(b"fixed-weight")
    if extra_weight:
        (snapshot / "second.safetensors").write_bytes(b"extra")
    return snapshot, hashlib.sha256(weight.read_bytes()).hexdigest()


def _runner(
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    del cwd, timeout
    assert environment["UV_OFFLINE"] == "1"
    if command[1] == "lock":
        return {"returncode": 0, "stdout": "", "stderr": "", "command": command}
    if command[0] == "nvidia-smi":
        return {"returncode": 0, "stdout": "GPU-1, Test, 1, 16384\n", "stderr": ""}
    payload = {
        "timesfm": "2.0.2",
        "torch": "2.9.1",
        "huggingface-hub": "0.36.2",
        "cuda_available": True,
        "cuda_device_count": 1,
    }
    return {"returncode": 0, "stdout": json.dumps(payload) + "\n", "stderr": ""}


def test_preflight_passes_with_pinned_offline_environment(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        _request(snapshot),
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=_runner,
    )
    assert report["status"] == "PASS"
    assert report["failed_checks"] == []


def test_preflight_fails_for_weight_hash_mismatch(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, _ = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        _request(snapshot),
        environment=environment,
        manifest=_manifest("0" * 64),
        project_root=tmp_path,
        runner=_runner,
    )
    assert report["status"] == "FAIL"
    assert "snapshot_weight_sha256" in report["failed_checks"]


def test_preflight_fails_when_lockfile_is_missing(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    (environment / "uv.lock").unlink()
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        _request(snapshot),
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=_runner,
    )
    assert "uv_lock_exists" in report["failed_checks"]


def test_preflight_rejects_multiple_weight_files(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path, extra_weight=True)
    environment = _environment(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        _request(snapshot),
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=_runner,
    )
    assert "snapshot_weight_count" in report["failed_checks"]


def test_preflight_detects_wrong_locked_version(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    lock = environment / "uv.lock"
    updated = lock.read_text().replace('version = "2.9.1"', 'version = "2.8.0"')
    lock.write_text(updated, encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        _request(snapshot),
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=_runner,
    )
    assert "locked_dependency:torch" in report["failed_checks"]


def test_preflight_detects_cuda_unavailable(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    def no_cuda(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
        result = _runner(command, cwd, env, timeout)
        if command[0] == "uv" and command[1] == "run":
            payload = json.loads(result["stdout"])
            payload["cuda_available"] = False
            payload["cuda_device_count"] = 0
            result["stdout"] = json.dumps(payload) + "\n"
        return result

    report = run_preflight(
        _request(snapshot),
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=no_cuda,
    )
    assert "torch_cuda_available" in report["failed_checks"]
    assert "torch_cuda_device_count" in report["failed_checks"]


def test_offline_environment_overrides_network_settings() -> None:
    environment = offline_environment({"UV_OFFLINE": "0", "OTHER": "kept"})
    assert environment["UV_OFFLINE"] == "1"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["PIP_NO_INDEX"] == "1"
    assert environment["OTHER"] == "kept"


def test_preflight_reports_malformed_lockfile(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    (environment / "uv.lock").write_text("not = [valid", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        _request(snapshot),
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=_runner,
    )
    assert report["status"] == "FAIL"
    assert "uv_lock_parse" in report["failed_checks"]


def test_preflight_requires_absolute_snapshot_path(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    request = _request(snapshot).model_copy(update={"snapshot_path": "relative/snapshot"})
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        request,
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=_runner,
    )
    assert "snapshot_path_explicit" in report["failed_checks"]


def test_preflight_rejects_manifest_identity_mismatch(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot, weight_hash = _snapshot(tmp_path)
    environment = _environment(tmp_path)
    request = _request(snapshot).model_copy(update={"repo_id": "wrong/repository"})
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    report = run_preflight(
        request,
        environment=environment,
        manifest=_manifest(weight_hash),
        project_root=tmp_path,
        runner=_runner,
    )
    assert "repo_id" in report["failed_checks"]
