from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from loto.darts_campaign.runtime_preflight import (
    RuntimeProfile,
    canonical_sha256,
    run_runtime_preflight,
)


def profile(**updates: object) -> RuntimeProfile:
    payload: dict[str, object] = {
        "profile_name": "darts-notorch",
        "package_versions": {"darts": "0.46.1", "numpy": "2.0.0"},
        "required_imports": ("darts", "numpy"),
        "required_model_exports": ("NaiveMean", "LinearRegressionModel"),
        "optional_imports": ("lightgbm",),
        "lockfile_path": "environments/darts-notorch/uv.lock",
        "smoke_models": ("NaiveMean", "LinearRegressionModel"),
    }
    payload.update(updates)
    return RuntimeProfile.model_validate(payload)


def importer(name: str) -> object:
    if name == "darts.models":
        return SimpleNamespace(NaiveMean=object(), LinearRegressionModel=object())
    if name in {"darts", "numpy", "torch"}:
        return SimpleNamespace()
    if name == "lightgbm":
        raise ModuleNotFoundError("No module named lightgbm", name="lightgbm")
    raise ModuleNotFoundError(name, name=name)


def versions(name: str) -> str:
    return {"darts": "0.46.1", "numpy": "2.0.0"}[name]


def create_lock(root: Path, relative: str) -> None:
    lock = root / relative
    lock.parent.mkdir(parents=True)
    lock.write_text("version = 1\n", encoding="utf-8")


def test_exact_darts_pin_is_required() -> None:
    with pytest.raises(ValidationError, match="darts==0.46.1"):
        profile(package_versions={"darts": "0.46.0"})


def test_cuda_profile_rejects_cpu_fallback() -> None:
    with pytest.raises(ValidationError, match="CPU fallback"):
        profile(require_cuda=True, allow_cpu_fallback=True)


def test_unsafe_lockfile_path_is_rejected() -> None:
    with pytest.raises(ValidationError, match="repository-relative"):
        profile(lockfile_path="../uv.lock")


def test_missing_lockfile_blocks(tmp_path: Path) -> None:
    report = run_runtime_preflight(
        profile(),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=importer,
        process_id=100,
    )
    assert report.overall_status == "BLOCKED"


def test_matching_runtime_passes(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-notorch/uv.lock")
    report = run_runtime_preflight(
        profile(),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=importer,
        process_id=101,
    )
    assert report.overall_status == "PASS"
    assert all(check.status in {"PASS", "SKIPPED"} for check in report.checks)


def test_version_drift_fails(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-notorch/uv.lock")

    def drift(name: str) -> str:
        return "0.46.0" if name == "darts" else "2.0.0"

    report = run_runtime_preflight(
        profile(),
        tmp_path,
        version_info=(3, 13),
        version_getter=drift,
        importer=importer,
        process_id=102,
    )
    assert report.overall_status == "FAIL"


def test_missing_required_import_blocks(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-notorch/uv.lock")

    def missing(name: str) -> object:
        if name == "darts":
            raise ModuleNotFoundError("No module named darts", name="darts")
        return importer(name)

    report = run_runtime_preflight(
        profile(),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=missing,
        process_id=103,
    )
    assert report.overall_status == "BLOCKED"


def test_missing_model_export_fails(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-notorch/uv.lock")

    def missing_export(name: str) -> object:
        if name == "darts.models":
            return SimpleNamespace(NaiveMean=object())
        return importer(name)

    report = run_runtime_preflight(
        profile(),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=missing_export,
        process_id=104,
    )
    assert report.overall_status == "FAIL"


class FakeCuda:
    def __init__(self, available: bool) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def device_count(self) -> int:
        return 1

    def current_device(self) -> int:
        return 0

    def get_device_name(self, _: int) -> str:
        return "Fake GPU"

    def synchronize(self, _: int) -> None:
        return None

    def memory_allocated(self, _: int) -> int:
        return 64

    def memory_reserved(self, _: int) -> int:
        return 128


class FakeTorch:
    def __init__(self, available: bool) -> None:
        self.cuda = FakeCuda(available)
        self.version = SimpleNamespace(cuda="13.0")

    def ones(self, *_: object, **__: object) -> object:
        return SimpleNamespace(device="cuda:0")


def torch_importer(available: bool):
    def load(name: str) -> object:
        if name == "torch":
            return FakeTorch(available)
        return importer(name)

    return load


def torch_profile(**updates: object) -> RuntimeProfile:
    return profile(
        profile_name="darts-torch",
        lockfile_path="environments/darts-torch/uv.lock",
        require_cuda=True,
        **updates,
    )


def test_cuda_unavailable_blocks(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-torch/uv.lock")
    report = run_runtime_preflight(
        torch_profile(),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=torch_importer(False),
        process_id=105,
    )
    assert report.overall_status == "BLOCKED"


def test_cuda_and_nvidia_pid_evidence_pass(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-torch/uv.lock")

    def runner(*_: object, **__: object) -> object:
        return SimpleNamespace(stdout="106, 512\n")

    report = run_runtime_preflight(
        torch_profile(require_nvidia_smi=True),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=torch_importer(True),
        nvidia_runner=runner,
        process_id=106,
    )
    assert report.overall_status == "PASS"


def test_malformed_nvidia_output_fails(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-torch/uv.lock")

    def runner(*_: object, **__: object) -> object:
        return SimpleNamespace(stdout="bad row\n")

    report = run_runtime_preflight(
        torch_profile(require_nvidia_smi=True),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=torch_importer(True),
        nvidia_runner=runner,
        process_id=107,
    )
    assert report.overall_status == "FAIL"


def test_report_hash_is_tamper_sensitive(tmp_path: Path) -> None:
    create_lock(tmp_path, "environments/darts-notorch/uv.lock")
    report = run_runtime_preflight(
        profile(),
        tmp_path,
        version_info=(3, 13),
        version_getter=versions,
        importer=importer,
        process_id=108,
    )
    payload = report.model_dump(mode="json")
    report_hash = payload.pop("report_sha256")
    assert report_hash == canonical_sha256(payload)
    payload["process_id"] = 109
    assert report_hash != canonical_sha256(payload)
