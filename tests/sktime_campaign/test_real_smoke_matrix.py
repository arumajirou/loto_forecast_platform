from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

from loto.sktime_campaign.matrix import run_smoke_matrix
from loto.sktime_campaign.protocol import ProviderOperation, ProviderRequest


def _formal_runtime_available() -> bool:
    try:
        return version("sktime") == "1.0.1" and bool(version("statsmodels"))
    except PackageNotFoundError:
        return False


@pytest.mark.skipif(
    not _formal_runtime_available(),
    reason="requires isolated sktime==1.0.1 classic-py312 runtime",
)
def test_real_classic_smoke_matrix(tmp_path: Path) -> None:
    request = ProviderRequest(
        operation=ProviderOperation.SMOKE_MATRIX,
        output_dir=str(tmp_path),
        environment_lane="classic-py312",
        forecast_horizon=[1, 2],
        series=[
            4,
            7,
            3,
            8,
            6,
            9,
            5,
            10,
            7,
            11,
            8,
            12,
            9,
            13,
            10,
            14,
            11,
            15,
            12,
            16,
            13,
            17,
            14,
            18,
        ],
    )

    payload = run_smoke_matrix(request, tmp_path)

    assert payload["status"] == "PASS"
    assert payload["summary"]["counts"]["PASS"] == 4
    assert payload["summary"]["all_requested_models_passed"] is True
    for result in payload["results"]:
        assert result["status"] == "PASS"
        assert result["prediction_finite"] is True
        assert result["save_load_status"] == "PASS"
        assert result["cpu_fallback"] is False
