from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.inventory import (
    CheckState,
    FormalAvailability,
    InventoryCategory,
    RuntimeInventory,
    RuntimeInventoryEntry,
)
from loto.adapters.gluonts.smoke import (
    DeepARCPUSmokeResult,
    SmokeOutcome,
    apply_deepar_smoke,
    run_deepar_cpu_smoke,
    smoke_sha256,
)


def _verified_result() -> DeepARCPUSmokeResult:
    checks = {
        name: CheckState.PASS
        for name in (
            "version",
            "import",
            "constructor",
            "dataset",
            "fit",
            "predict",
            "shape",
            "finite",
            "device",
        )
    }
    return DeepARCPUSmokeResult(
        lane="compat",
        outcome=SmokeOutcome.VERIFIED,
        started_at_utc="2026-08-05T00:00:00+00:00",
        finished_at_utc="2026-08-05T00:00:01+00:00",
        duration_seconds=1.0,
        process_id=1,
        seed=1,
        prediction_length=1,
        context_length=8,
        expected_shape=[1],
        observed_shape=[1],
        prediction_values=[2.5],
        observed_devices=["cpu"],
        checks=checks,
    )


def test_verified_smoke_requires_every_runtime_check() -> None:
    payload = _verified_result().model_dump(mode="json")
    payload["checks"]["fit"] = "FAIL"

    with pytest.raises(ValidationError, match="every required check"):
        DeepARCPUSmokeResult.model_validate(payload)


def test_skip_environment_blocks_without_claiming_runtime_success(monkeypatch) -> None:
    monkeypatch.setenv("LOTO_GLUONTS_SKIP_DEEPAR_SMOKE", "1")

    result = run_deepar_cpu_smoke("compat")

    assert result.outcome is SmokeOutcome.BLOCKED
    assert result.checks["version"] is CheckState.BLOCKED
    assert result.prediction_values == []
    assert result.errors
    assert len(smoke_sha256(result)) == 64


def test_verified_smoke_promotes_only_deepar_inventory_entry() -> None:
    inventory = RuntimeInventory(
        lane="compat",
        entries=[
            RuntimeInventoryEntry(
                name="DeepAREstimator",
                category=InventoryCategory.PYTORCH_ESTIMATOR,
                module="gluonts.torch",
                import_state=CheckState.PASS,
                export_state=CheckState.PASS,
                class_state=CheckState.PASS,
                signature_state=CheckState.PASS,
                formal_availability=FormalAvailability.DISCOVERED_ONLY,
            ),
            RuntimeInventoryEntry(
                name="PatchTSTEstimator",
                category=InventoryCategory.PYTORCH_ESTIMATOR,
                module="gluonts.torch",
                formal_availability=FormalAvailability.EXECUTION_PENDING,
            ),
        ],
    )

    updated = apply_deepar_smoke(inventory, _verified_result())

    assert updated.entries[0].formal_availability is FormalAvailability.VERIFIED
    assert updated.entries[0].constructor_state is CheckState.PASS
    assert updated.entries[0].fit_state is CheckState.PASS
    assert updated.entries[0].predict_state is CheckState.PASS
    assert updated.entries[0].device_state is CheckState.PASS
    assert updated.entries[1].formal_availability is FormalAvailability.EXECUTION_PENDING
    assert updated.summary["formally_verified"] == 1


def test_smoke_lane_must_match_inventory_lane() -> None:
    inventory = RuntimeInventory(lane="latest", entries=[])

    with pytest.raises(ValueError, match="lane mismatch"):
        apply_deepar_smoke(inventory, _verified_result())


def test_fake_runtime_exercises_verified_fit_predict_path(monkeypatch) -> None:
    import sys
    import types

    import numpy as np

    import loto.adapters.gluonts.smoke as smoke_module

    monkeypatch.delenv("LOTO_GLUONTS_SKIP_DEEPAR_SMOKE", raising=False)
    monkeypatch.setattr(
        smoke_module,
        "runtime_versions",
        lambda: {
            "gluonts": "0.16.3",
            "torch": "2.9.1",
            "lightning": "2.4.0",
            "pytorch_lightning": "2.4.0",
            "numpy": "2.3.5",
            "pandas": "2.3.1",
        },
    )

    modules = {
        name: types.ModuleType(name)
        for name in (
            "gluonts",
            "gluonts.dataset",
            "gluonts.dataset.common",
            "gluonts.torch",
            "gluonts.torch.distributions",
            "gluonts.torch.model",
            "gluonts.torch.model.deepar",
        )
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    class FakeListDataset(list):
        def __init__(self, data, freq):
            super().__init__(data)
            self.freq = freq

    class FakeStudentTOutput:
        pass

    class FakeParameter:
        device = "cpu"

    class FakeNetwork:
        def parameters(self):
            return iter([FakeParameter()])

    class FakeForecast:
        mean = np.asarray([3.5], dtype=float)

    class FakePredictor:
        prediction_net = FakeNetwork()

        def predict(self, dataset):
            del dataset
            yield FakeForecast()

    class FakeDeepAREstimator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def train(self, training_data):
            del training_data
            return FakePredictor()

    modules["gluonts.dataset.common"].ListDataset = FakeListDataset
    modules["gluonts.torch.distributions"].StudentTOutput = FakeStudentTOutput
    modules["gluonts.torch.model.deepar"].DeepAREstimator = FakeDeepAREstimator

    result = run_deepar_cpu_smoke("compat")

    assert result.outcome is SmokeOutcome.VERIFIED
    assert result.prediction_values == [3.5]
    assert result.observed_devices == ["cpu"]
    assert all(state is CheckState.PASS for state in result.checks.values())
