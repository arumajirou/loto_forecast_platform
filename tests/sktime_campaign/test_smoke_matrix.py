from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from loto.sktime_campaign import matrix
from loto.sktime_campaign.matrix import (
    SmokeModelSpec,
    run_smoke_matrix,
    summarize_matrix_results,
)
from loto.sktime_campaign.protocol import (
    ProviderOperation,
    ProviderRequest,
    SmokeModelId,
)


class FakeForecaster:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.cutoff = None

    def fit(self, y, fh):
        self.cutoff = int(y.index[-1])
        return self

    def predict(self, fh):
        index = [self.cutoff + int(step) for step in fh]
        return pd.Series([7.0] * len(index), index=index, name="y")

    def get_tags(self):
        return {
            "capability:missing_values": False,
            "capability:pred_int": False,
            "property:randomness": "deterministic",
            "requires-fh-in-fit": False,
        }

    def save(self, path):
        archive_path = Path(f"{path}.zip")
        archive = zipfile.ZipFile(archive_path, "w")
        archive.writestr("state.txt", str(self.cutoff))
        return archive

    @classmethod
    def load_from_path(cls, path):
        with zipfile.ZipFile(path) as archive:
            cutoff = int(archive.read("state.txt").decode("utf-8"))
        instance = cls()
        instance.cutoff = cutoff
        return instance


def _request(tmp_path: Path, model_ids: list[SmokeModelId]) -> ProviderRequest:
    return ProviderRequest(
        operation=ProviderOperation.SMOKE_MATRIX,
        output_dir=str(tmp_path),
        environment_lane="classic-py312",
        model_ids=model_ids,
        forecast_horizon=[1, 2],
        series=[1, 2, 3, 4, 5],
    )


def test_request_rejects_duplicate_model_ids(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        _request(
            tmp_path,
            [SmokeModelId.NAIVE_LAST, SmokeModelId.NAIVE_LAST],
        )


def test_smoke_matrix_passes_when_every_model_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix, "_load_class", lambda _: FakeForecaster)
    model_ids = [
        SmokeModelId.NAIVE_LAST,
        SmokeModelId.POLYNOMIAL_TREND_D1,
    ]
    specs = {
        model_id: SmokeModelSpec(
            model_id=model_id,
            class_path=f"fake.{model_id.value}",
            constructor={},
            required_distributions=(),
        )
        for model_id in model_ids
    }

    payload = run_smoke_matrix(
        _request(tmp_path, model_ids),
        tmp_path,
        specs=specs,
    )

    assert payload["status"] == "PASS"
    assert payload["summary"]["all_requested_models_passed"] is True
    assert [row["status"] for row in payload["results"]] == ["PASS", "PASS"]
    assert all(row["save_load_status"] == "PASS" for row in payload["results"])


def test_matrix_is_partial_when_one_model_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix, "_load_class", lambda _: FakeForecaster)
    available = SmokeModelId.NAIVE_LAST
    unavailable = SmokeModelId.THETA
    specs = {
        available: SmokeModelSpec(
            model_id=available,
            class_path="fake.available",
            constructor={},
            required_distributions=(),
        ),
        unavailable: SmokeModelSpec(
            model_id=unavailable,
            class_path="fake.unavailable",
            constructor={},
            required_distributions=("definitely-not-installed-distribution",),
        ),
    }

    payload = run_smoke_matrix(
        _request(tmp_path, [available, unavailable]),
        tmp_path,
        specs=specs,
    )

    assert payload["status"] == "PARTIAL"
    assert payload["summary"]["counts"]["PASS"] == 1
    assert payload["summary"]["counts"]["UNAVAILABLE"] == 1
    assert payload["results"][1]["failed_phase"] == "dependency"


def test_summary_fails_when_no_model_passes() -> None:
    summary = summarize_matrix_results(
        [
            {"status": "FAILED"},
            {"status": "UNAVAILABLE"},
        ]
    )

    assert summary["status"] == "FAILED"
    assert summary["all_requested_models_passed"] is False


def test_smoke_matrix_rejects_core_py313_lane(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="classic-py312"):
        ProviderRequest(
            operation=ProviderOperation.SMOKE_MATRIX,
            output_dir=str(tmp_path),
            environment_lane="core-py313",
        )
