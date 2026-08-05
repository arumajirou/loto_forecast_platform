from __future__ import annotations

import hashlib
import sys
import types
from dataclasses import dataclass

import torch
from torch import nn

from loto.basicts_campaign import runtime
from loto.basicts_campaign.protocol import ProviderOperation, ProviderRequest, ProviderStatus


@dataclass
class FakeConfig:
    input_len: int
    output_len: int
    num_features: int = 1
    moving_avg: int = 3
    stride: int = 1
    individual: bool = False


class FakeDLinear(nn.Module):
    def __init__(self, config: FakeConfig):
        super().__init__()
        self.linear = nn.Linear(config.input_len, config.output_len)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        values = inputs.transpose(1, 2)
        return self.linear(values).transpose(1, 2)


def install_fake_basicts(monkeypatch) -> None:
    modules = {
        "basicts": types.ModuleType("basicts"),
        "basicts.models": types.ModuleType("basicts.models"),
        "basicts.models.DLinear": types.ModuleType("basicts.models.DLinear"),
        "basicts.models.DLinear.arch": types.ModuleType("basicts.models.DLinear.arch"),
        "basicts.models.DLinear.config": types.ModuleType("basicts.models.DLinear.config"),
        "basicts.models.DLinear.arch.dlinear_arch": types.ModuleType(
            "basicts.models.DLinear.arch.dlinear_arch"
        ),
        "basicts.models.DLinear.config.dlinear_config": types.ModuleType(
            "basicts.models.DLinear.config.dlinear_config"
        ),
    }
    modules["basicts.models.DLinear.arch.dlinear_arch"].DLinear = FakeDLinear
    modules["basicts.models.DLinear.config.dlinear_config"].DLinearConfig = FakeConfig
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def assert_sha256sums(run_dir) -> None:
    lines = (run_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    for line in lines:
        expected, relative = line.split("  ", 1)
        actual = hashlib.sha256((run_dir / relative).read_bytes()).hexdigest()
        assert actual == expected


def expected_revision() -> str:
    return ProviderRequest.model_fields["expected_upstream_revision"].default


def provenance() -> dict[str, object]:
    revision = expected_revision()
    package_init = "/venv/site-packages/basicts/__init__.py"
    return {
        "installed_provenance_status": "PASS",
        "installed_record_integrity_status": "PASS",
        "distribution_name": "BasicTS",
        "distribution_version": "1.1.0",
        "direct_url_repository": "https://github.com/GestaltCogTeam/BasicTS",
        "direct_url_vcs": "git",
        "direct_url_commit_id": revision,
        "direct_url_requested_revision": revision,
        "direct_url_sha256": "a" * 64,
        "direct_url_record_status": "PASS",
        "direct_url_record_entry": "BasicTS-1.1.0.dist-info/direct_url.json",
        "direct_url_record_path": (
            "/venv/site-packages/BasicTS-1.1.0.dist-info/direct_url.json"
        ),
        "direct_url_record_hash_mode": "sha256",
        "direct_url_record_hash_value": "A" * 43,
        "direct_url_record_size_bytes": 200,
        "import_origin_status": "PASS",
        "import_name": "basicts",
        "import_provider_distributions": ["BasicTS"],
        "distribution_package_entry": "basicts/__init__.py",
        "distribution_package_init": package_init,
        "import_spec_origin": package_init,
        "import_submodule_search_locations": ["/venv/site-packages/basicts"],
        "import_origin_sha256": "b" * 64,
        "module_already_loaded": False,
        "package_init_record_status": "PASS",
        "package_init_record_hash_mode": "sha256",
        "package_init_record_hash_value": "B" * 43,
        "package_init_record_size_bytes": 120,
    }


def test_identity_and_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runtime, "installed_basicts_version", lambda: "1.1.0")
    monkeypatch.setattr(runtime, "verify_installed_basicts_provenance", provenance)
    monkeypatch.setenv(runtime.REVISION_ENV, expected_revision())
    request = ProviderRequest(
        operation=ProviderOperation.IDENTITY,
        output_dir=str(tmp_path),
    )
    response = runtime.execute_request(request)
    assert response.status is ProviderStatus.PASS
    assert response.evidence["installed_provenance_status"] == "PASS"
    assert response.evidence["installed_record_integrity_status"] == "PASS"
    assert response.evidence["import_origin_status"] == "PASS"
    assert response.evidence["direct_url_commit_id"] == expected_revision()
    assert (tmp_path / "ARTIFACT_MANIFEST.json").is_file()
    assert_sha256sums(tmp_path)


def test_identity_rejects_provenance_version_drift(monkeypatch, tmp_path) -> None:
    bad = provenance()
    bad["distribution_version"] = "0.0.0"
    monkeypatch.setattr(runtime, "installed_basicts_version", lambda: "1.1.0")
    monkeypatch.setattr(runtime, "verify_installed_basicts_provenance", lambda: bad)
    monkeypatch.setenv(runtime.REVISION_ENV, expected_revision())
    request = ProviderRequest(
        operation=ProviderOperation.IDENTITY,
        output_dir=str(tmp_path),
    )

    response = runtime.execute_request(request)

    assert response.status is ProviderStatus.FAILED
    assert "provenance metadata differ" in response.error["message"]


def test_identity_rejects_record_integrity_drift(monkeypatch, tmp_path) -> None:
    bad = provenance()
    bad["package_init_record_status"] = "FAILED"
    monkeypatch.setattr(runtime, "installed_basicts_version", lambda: "1.1.0")
    monkeypatch.setattr(runtime, "verify_installed_basicts_provenance", lambda: bad)
    monkeypatch.setenv(runtime.REVISION_ENV, expected_revision())
    request = ProviderRequest(
        operation=ProviderOperation.IDENTITY,
        output_dir=str(tmp_path),
    )

    response = runtime.execute_request(request)

    assert response.status is ProviderStatus.FAILED
    assert "package __init__.py RECORD integrity" in response.error["message"]


def test_identity_rejects_import_origin_drift(monkeypatch, tmp_path) -> None:
    bad = provenance()
    bad["import_spec_origin"] = "/shadow/basicts/__init__.py"
    monkeypatch.setattr(runtime, "installed_basicts_version", lambda: "1.1.0")
    monkeypatch.setattr(runtime, "verify_installed_basicts_provenance", lambda: bad)
    monkeypatch.setenv(runtime.REVISION_ENV, expected_revision())
    request = ProviderRequest(
        operation=ProviderOperation.IDENTITY,
        output_dir=str(tmp_path),
    )

    response = runtime.execute_request(request)

    assert response.status is ProviderStatus.FAILED
    assert "import origin differs" in response.error["message"]


def test_dlinear_smoke_fit_save_load(monkeypatch, tmp_path) -> None:
    install_fake_basicts(monkeypatch)
    monkeypatch.setattr(runtime, "installed_basicts_version", lambda: "1.1.0")
    monkeypatch.setattr(runtime, "verify_installed_basicts_provenance", provenance)
    monkeypatch.setenv(runtime.REVISION_ENV, expected_revision())
    request = ProviderRequest(
        operation=ProviderOperation.DLINEAR_SMOKE,
        output_dir=str(tmp_path),
        series=[[float(index), float(index + 1)] for index in range(12)],
        input_len=6,
        output_len=1,
        moving_avg=3,
        training_steps=2,
    )
    response = runtime.execute_request(request)
    assert response.status is ProviderStatus.PASS
    assert response.evidence["prediction_shape"] == [1, 1, 2]
    assert response.evidence["save_load_exact_match"] is True
    assert response.evidence["cpu_fallback"] is False
    assert_sha256sums(tmp_path)
