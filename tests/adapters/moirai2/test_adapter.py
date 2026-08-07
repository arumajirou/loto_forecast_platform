from __future__ import annotations

import pandas as pd
import pytest

from loto.adapters.moirai2.adapter import Moirai2Adapter, Moirai2AdapterError
from loto.moirai2_campaign.geometry import geometry_for_game


def test_adapter_builds_dynamic_geometry_request() -> None:
    history = pd.DataFrame(
        [{f"n{position}": position + row for position in range(1, 6)} for row in range(140)]
    )
    adapter = Moirai2Adapter(runtime_lane="supported-py311")
    request = adapter.build_request(
        history,
        run_id="mini-test",
        geometry=geometry_for_game("miniloto"),
        position_columns=["n1", "n2", "n3", "n4", "n5"],
        context_length=128,
        prediction_length=5,
    )
    assert request.game_geometry.game_id == "miniloto"
    assert request.context_length == 128
    assert request.prediction_length == 5


def test_adapter_rejects_formal_cpu_fallback() -> None:
    adapter = Moirai2Adapter(runtime_lane="cuda13-experimental")
    payload = {
        "status": "OK",
        "phase": "predict",
        "message": "bad fallback",
        "runtime_evidence": {
            "process_id": 1,
            "package_version": "2.0.0",
            "runtime_lane": "cuda13-experimental",
            "requested_device": "cuda",
            "execution_device": "cpu",
            "model_parameter_device": "cpu",
            "output_shape": [1, 1],
            "all_quantiles_finite": True,
            "quantile_monotonicity": True,
            "cpu_fallback": True,
        },
        "gpu_evidence": {
            "requested_device": "cuda",
            "execution_device": "cpu",
            "cuda_available": False,
            "provider_pid": 1,
            "gpu_pid": None,
            "peak_vram_bytes": 0,
            "cpu_fallback": True,
        },
    }
    with pytest.raises(Moirai2AdapterError, match="formal execution forbids CPU fallback"):
        adapter.parse_response(payload)


def test_adapter_does_not_silently_shorten_context() -> None:
    history = pd.DataFrame([{"n1": float(row)} for row in range(8)])
    adapter = Moirai2Adapter(runtime_lane="supported-py311")
    with pytest.raises(ValueError, match="at least context_length"):
        adapter.build_request(
            history,
            run_id="short-history",
            geometry=geometry_for_game("numbers3").model_copy(
                update={"position_count": 1, "game_id": "numbers3-n1"}
            ),
            position_columns=["n1"],
            context_length=16,
        )
