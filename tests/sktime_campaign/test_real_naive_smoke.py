from __future__ import annotations

from importlib.metadata import version
from importlib.util import find_spec

import pytest

from loto.sktime_campaign.protocol import ProviderRequest
from loto.sktime_campaign.runtime import run_naive_smoke

pytestmark = pytest.mark.skipif(
    find_spec("sktime") is None,
    reason="sktime is isolated from the default project test environment",
)


def test_real_naive_fit_predict_save_load(tmp_path) -> None:
    if version("sktime") != "1.0.1":
        pytest.skip("formal smoke is pinned to sktime==1.0.1")

    request = ProviderRequest(
        operation="naive_smoke",
        output_dir=str(tmp_path),
        forecast_horizon=[1, 2],
        series=[4, 7, 3, 8, 6, 9, 5, 10],
        save_load=True,
    )

    result = run_naive_smoke(request, tmp_path)

    assert result["fit_status"] == "PASS"
    assert result["predict_status"] == "PASS"
    assert result["prediction_shape"] == [2]
    assert result["prediction_finite"] is True
    assert result["prediction_before_save"] == result["prediction_after_load"]
    assert result["save_load"]["status"] == "PASS"
    assert (tmp_path / "naive_forecaster.zip").is_file()
