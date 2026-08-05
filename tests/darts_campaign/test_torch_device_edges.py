from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from loto.darts_campaign import torch_models
from loto.darts_campaign.protocol import GameGeometry
from loto.darts_campaign.torch_models import (
    TorchCampaignConfig,
    TorchDeviceContract,
    TorchModelConfig,
    TorchRuntimeObservation,
    TorchTrainingContract,
    certify_device_use,
    run_torch_matrix,
)


class FakeSeries:
    @classmethod
    def from_series(cls, series: pd.Series) -> np.ndarray:
        return series.to_numpy(float)


def test_device_mismatch_fallback_and_package_import_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = TorchRuntimeObservation(
        torch_cuda_available=True,
        requested_accelerator="cpu",
        effective_accelerator="gpu",
        model_parameter_devices=("cuda:0",),
        prediction_device="cuda:0",
        process_pid=100,
        gpu_pid=100,
        device_index=0,
        vram_before_bytes=1,
        vram_peak_bytes=2,
        vram_after_bytes=1,
        cuda_allocated_bytes=1,
        cuda_reserved_bytes=2,
    )
    mismatch = certify_device_use(TorchDeviceContract(), observation)
    assert mismatch["status"] == "RUNTIME_EVIDENCE_MISMATCH"
    with pytest.raises(ValueError, match="forbids CPU fallback"):
        TorchDeviceContract(allow_cpu_fallback=True)

    config = TorchCampaignConfig(
        run_id="missing-darts",
        models=(TorchModelConfig(public_name="NBEATSModel"),),
        training=TorchTrainingContract(input_chunk_length=2),
        series_layout="position_local",
    )
    frame = pd.DataFrame({"draw_no": [1, 2, 3], "N1": [1, 2, 3]})
    geometry = GameGeometry(
        game_id="test",
        positions=1,
        min_value=0,
        max_value=9,
        draw_no_col="draw_no",
        position_prefix="N",
    )

    def fail_import(_: str) -> None:
        raise ModuleNotFoundError("darts is unavailable")

    monkeypatch.setattr(torch_models.importlib, "import_module", fail_import)
    result = run_torch_matrix(
        config,
        frame,
        geometry,
        timeseries_cls=FakeSeries,
        runtime_probe=lambda *_: observation,
    )[0]
    assert result.failure_class == "DEPENDENCY_MISSING"
    assert "darts is unavailable" in (result.message or "")
