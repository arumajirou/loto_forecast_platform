from __future__ import annotations

from pathlib import Path

import pytest

from loto.moirai2_campaign.runtime_preflight import (
    RuntimePreflightError,
    parse_exact_dependencies,
    parse_lock_versions,
    validate_lane_files,
)


PYPROJECT = """
[project]
name = "test-lane"
version = "0.1.0"
dependencies = [
  "uni2ts==2.0.0",
  "gluonts==0.14.4",
  "huggingface-hub==0.36.2",
  "numpy==1.26.4",
  "pandas==2.2.3",
  "torch==2.4.1",
]
""".strip()

LOCK = """
version = 1

[[package]]
name = "uni2ts"
version = "2.0.0"

[[package]]
name = "gluonts"
version = "0.14.4"

[[package]]
name = "huggingface-hub"
version = "0.36.2"

[[package]]
name = "numpy"
version = "1.26.4"

[[package]]
name = "pandas"
version = "2.2.3"

[[package]]
name = "torch"
version = "2.4.1"
""".strip()


def _lane(tmp_path: Path) -> tuple[Path, Path]:
    environment = tmp_path / "environment"
    snapshot = tmp_path / "snapshot"
    environment.mkdir()
    snapshot.mkdir()
    (environment / "pyproject.toml").write_text(PYPROJECT + "\n", encoding="utf-8")
    (environment / "uv.lock").write_text(LOCK + "\n", encoding="utf-8")
    (snapshot / "config.json").write_text("{}\n", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"weights")
    return environment, snapshot


def test_exact_dependency_and_lock_parsing(tmp_path: Path) -> None:
    environment, _ = _lane(tmp_path)
    dependencies = parse_exact_dependencies(environment / "pyproject.toml")
    locks = parse_lock_versions(environment / "uv.lock")
    assert dependencies["uni2ts"] == "2.0.0"
    assert dependencies["torch"] == "2.4.1"
    assert locks["torch"] == {"2.4.1"}


def test_lane_validation_retains_hashes_and_versions(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    evidence = validate_lane_files(environment, snapshot)
    assert len(evidence["pyproject_sha256"]) == 64
    assert len(evidence["lock_sha256"]) == 64
    assert evidence["dependency_pins"]["uni2ts"] == "2.0.0"
    assert evidence["snapshot_files"]["model.safetensors"]


def test_missing_lock_fails_closed(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    (environment / "uv.lock").unlink()
    with pytest.raises(RuntimePreflightError, match="reviewed uv.lock is required"):
        validate_lane_files(environment, snapshot)


def test_lock_version_mismatch_fails_closed(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    changed = LOCK.replace('version = "2.0.0"', 'version = "1.9.0"', 1)
    (environment / "uv.lock").write_text(changed + "\n", encoding="utf-8")
    with pytest.raises(RuntimePreflightError, match="does not resolve exact pins"):
        validate_lane_files(environment, snapshot)


def test_missing_snapshot_weight_fails_closed(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    (snapshot / "model.safetensors").unlink()
    with pytest.raises(RuntimePreflightError, match="snapshot required files are missing"):
        validate_lane_files(environment, snapshot)


def test_frozen_probe_validates_cpu_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, _ = _lane(tmp_path)

    class Result:
        returncode = 0
        stderr = ""
        stdout = (
            '{"cuda_visible_devices":"","gluonts_version":"0.14.4",'
            '"huggingface_hub_version":"0.36.2","numpy_version":"1.26.4",'
            '"pandas_version":"2.2.3","python_executable":"/tmp/python",'
            '"python_version":"3.11","torch_cuda_available":false,'
            '"torch_cuda_device_count":0,"torch_cuda_version":null,'
            '"torch_version":"2.4.1","uni2ts_version":"2.0.0"}'
        )

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Result())
    from loto.moirai2_campaign.runtime_preflight import run_frozen_probe

    payload = run_frozen_probe(
        environment_path=environment,
        requested_device="cpu",
    )
    assert payload["uni2ts_version"] == "2.0.0"
    assert payload["cuda_visible_devices"] == ""


def test_frozen_probe_rejects_unavailable_cuda(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, _ = _lane(tmp_path)

    class Result:
        returncode = 0
        stderr = ""
        stdout = (
            '{"cuda_visible_devices":null,"gluonts_version":"0.14.4",'
            '"huggingface_hub_version":"0.36.2","numpy_version":"1.26.4",'
            '"pandas_version":"2.2.3","python_executable":"/tmp/python",'
            '"python_version":"3.11","torch_cuda_available":false,'
            '"torch_cuda_device_count":0,"torch_cuda_version":null,'
            '"torch_version":"2.4.1","uni2ts_version":"2.0.0"}'
        )

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Result())
    from loto.moirai2_campaign.runtime_preflight import run_frozen_probe

    with pytest.raises(RuntimePreflightError, match="CUDA was requested"):
        run_frozen_probe(
            environment_path=environment,
            requested_device="cuda",
        )
