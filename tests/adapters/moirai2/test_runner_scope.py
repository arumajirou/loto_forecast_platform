from __future__ import annotations

import pytest

from loto.adapters.moirai2.contracts import Moirai2ProviderRequest
from scripts.run_moirai2_provider import run_provider


def test_p0_p6_runner_rejects_covariate_runtime_before_importing_uni2ts() -> None:
    history = [{"n1": float(index)} for index in range(16)]
    request = Moirai2ProviderRequest.model_validate(
        {
            "run_id": "p7-deferred",
            "license_lane": "personal_noncommercial_research",
            "game_geometry": {
                "game_id": "numbers3-n1",
                "position_count": 1,
                "candidate_min": 0,
                "candidate_max": 9,
                "strictly_increasing": False,
            },
            "series_layout": "position_univariate",
            "position_columns": ["n1"],
            "history": history,
            "context_length": 16,
            "past_covariates": {"frequency": [1.0] * 16},
        }
    )
    with pytest.raises(RuntimeError, match="deferred.*P7"):
        run_provider(request, runtime_lane="supported-py311")
