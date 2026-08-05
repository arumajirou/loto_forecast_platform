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


def test_identity_and_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runtime, "installed_basicts_version", lambda: "1.1.0")
    monkeypatch.setenv(runtime.REVISION_ENV, expected_revision())
    request = ProviderRequest(
        operation=ProviderOperation.IDENTITY,
        output_dir=str(tmp_path),
    )
    response = runtime.execute_request(request)
    assert response.status is ProviderStatus.PASS
    assert (tmp_path / "ARTIFACT_MANIFEST.json").is_file()
    assert_sha256sums(tmp_path)


def test_dlinear_smoke_fit_save_load(monkeypatch, tmp_path) -> None:
    install_fake_basicts(monkeypatch)
    monkeypatch.setattr(runtime, "installed_basicts_version", lambda: "1.1.0")
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
