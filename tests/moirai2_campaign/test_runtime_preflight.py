from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.moirai2_campaign.lock_review import (
    APPROVAL_FILENAME,
    REPORT_FILENAME,
    build_approval,
    inspect_lock,
)
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

HASH = "sha256:" + ("a" * 64)

LOCK = f"""
version = 1

[[package]]
name = "test-lane"
version = "0.1.0"
source = {{ virtual = "." }}
dependencies = [
  {{ name = "uni2ts" }},
  {{ name = "gluonts" }},
  {{ name = "huggingface-hub" }},
  {{ name = "numpy" }},
  {{ name = "pandas" }},
  {{ name = "torch" }},
]

[[package]]
name = "uni2ts"
version = "2.0.0"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/uni2ts.tar.gz", hash = "{HASH}", size = 1 }}

[[package]]
name = "gluonts"
version = "0.14.4"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/gluonts.tar.gz", hash = "{HASH}", size = 1 }}

[[package]]
name = "huggingface-hub"
version = "0.36.2"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/hf.tar.gz", hash = "{HASH}", size = 1 }}

[[package]]
name = "numpy"
version = "1.26.4"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/numpy.tar.gz", hash = "{HASH}", size = 1 }}

[[package]]
name = "pandas"
version = "2.2.3"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/pandas.tar.gz", hash = "{HASH}", size = 1 }}
dependencies = [{{ name = "numpy" }}]

[[package]]
name = "torch"
version = "2.4.1"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/torch.tar.gz", hash = "{HASH}", size = 1 }}
""".strip()


def _lane(tmp_path: Path) -> tuple[Path, Path]:
    environment = tmp_path / "environment"
    snapshot = tmp_path / "snapshot"
    environment.mkdir()
    snapshot.mkdir()
    pyproject_path = environment / "pyproject.toml"
    lock_path = environment / "uv.lock"
    pyproject_path.write_text(PYPROJECT + "\n", encoding="utf-8")
    lock_path.write_text(LOCK + "\n", encoding="utf-8")
    report = inspect_lock(
        pyproject_path=pyproject_path,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    approval = build_approval(
        report=report,
        reviewer="reviewer",
        reviewed_at="2026-08-06T00:00:00+09:00",
    )
    (environment / REPORT_FILENAME).write_text(
        json.dumps(report, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (environment / APPROVAL_FILENAME).write_text(
        json.dumps(approval, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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


def test_lane_validation_retains_review_hashes_and_versions(
    tmp_path: Path,
) -> None:
    environment, snapshot = _lane(tmp_path)
    evidence = validate_lane_files(
        environment,
        snapshot,
        runtime_lane="supported-py311",
    )
    assert len(evidence["pyproject_sha256"]) == 64
    assert len(evidence["lock_sha256"]) == 64
    assert evidence["lock_review"]["reviewer"] == "reviewer"
    assert evidence["dependency_pins"]["uni2ts"] == "2.0.0"
    assert evidence["snapshot_files"]["model.safetensors"]


def test_missing_lock_review_approval_fails_closed(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    (environment / APPROVAL_FILENAME).unlink()
    with pytest.raises(RuntimePreflightError, match="reviewed lock validation failed"):
        validate_lane_files(
            environment,
            snapshot,
            runtime_lane="supported-py311",
        )


def test_tampered_lock_fails_before_runtime(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    with (environment / "uv.lock").open("a", encoding="utf-8") as stream:
        stream.write("# changed\n")
    with pytest.raises(RuntimePreflightError, match="lock_sha256"):
        validate_lane_files(
            environment,
            snapshot,
            runtime_lane="supported-py311",
        )


def test_lock_version_mismatch_fails_closed(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    changed = LOCK.replace(
        'name = "uni2ts"\nversion = "2.0.0"',
        'name = "uni2ts"\nversion = "1.9.0"',
    )
    (environment / "uv.lock").write_text(changed + "\n", encoding="utf-8")
    with pytest.raises(RuntimePreflightError, match="lock_sha256"):
        validate_lane_files(
            environment,
            snapshot,
            runtime_lane="supported-py311",
        )


def test_missing_snapshot_weight_fails_closed(tmp_path: Path) -> None:
    environment, snapshot = _lane(tmp_path)
    (snapshot / "model.safetensors").unlink()
    with pytest.raises(RuntimePreflightError, match="snapshot required files are missing"):
        validate_lane_files(
            environment,
            snapshot,
            runtime_lane="supported-py311",
        )


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
