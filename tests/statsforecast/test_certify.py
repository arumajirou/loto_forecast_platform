from __future__ import annotations

import pickle
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from loto.statsforecast.certify import (
    TARGET_VERSION,
    certify_installed_runtime,
    compare_predictions,
)


class FakeNaive:
    uses_exog = False

    def __init__(self, alias: str = "Naive") -> None:
        self.alias = alias


class FakeStatsForecast:
    def __init__(self, *, models, freq, n_jobs) -> None:
        self.models = models
        self.freq = freq
        self.n_jobs = n_jobs
        self._ids: list[str] = []
        self._last_ds: dict[str, int] = {}

    def forecast(self, *, df, h, level):
        return self._prediction(df, h)

    def fit(self, *, df):
        self._ids = [str(value) for value in df["unique_id"].unique()]
        self._last_ds = {
            str(unique_id): int(group["ds"].max())
            for unique_id, group in df.groupby("unique_id", sort=False)
        }
        return self

    def predict(self, *, h):
        rows = []
        for unique_id in self._ids:
            for step in range(1, h + 1):
                rows.append(
                    {
                        "unique_id": unique_id,
                        "ds": self._last_ds[unique_id] + step,
                        "Naive": 1.0,
                    }
                )
        return pd.DataFrame(rows)

    def save(self, *, path) -> None:
        with Path(path).open("wb") as stream:
            pickle.dump(self, stream)

    @staticmethod
    def load(path):
        with Path(path).open("rb") as stream:
            return pickle.load(stream)

    @staticmethod
    def _prediction(df, h):
        rows = []
        for unique_id, group in df.groupby("unique_id", sort=False):
            last_ds = int(group["ds"].max())
            for step in range(1, h + 1):
                rows.append({"unique_id": unique_id, "ds": last_ds + step, "Naive": 1.0})
        return pd.DataFrame(rows)


def test_prediction_comparison_detects_equal_lifecycle_outputs() -> None:
    frame = pd.DataFrame({"unique_id": ["a"], "ds": [2], "Naive": [1.0]})
    result = compare_predictions(frame, frame.copy(deep=True))
    assert result["passed"] is True
    assert result["max_abs_diff"] == 0.0


def test_certifier_writes_durable_partial_bundle_for_selected_model(tmp_path) -> None:
    module = SimpleNamespace(__all__=("Naive",), Naive=FakeNaive)
    run_dir = certify_installed_runtime(
        tmp_path,
        run_id="runtime-test",
        selected_models=["Naive"],
        core_class=FakeStatsForecast,
        models_module=module,
        injected_version=TARGET_VERSION,
    )
    assert (run_dir / "CONFIG.json").is_file()
    assert (run_dir / "MODEL_RUNTIME_MATRIX.json").is_file()
    assert (run_dir / "VERIFICATION_REPORT.json").is_file()
    assert (run_dir / "ARTIFACT_MANIFEST.json").is_file()
    assert (run_dir / "SHA256SUMS").is_file()
    result = pd.read_json(run_dir / "MODEL_RUNTIME_MATRIX.json").iloc[0]
    assert result["status"] == "VERIFIED"
    report = pd.read_json(run_dir / "VERIFICATION_REPORT.json", typ="series")
    assert bool(report["formal_pass"]) is False
    assert report["status"] == "PARTIALLY_VERIFIED"


def test_missing_distribution_is_retained_as_partial_evidence(tmp_path) -> None:
    run_dir = certify_installed_runtime(
        tmp_path,
        run_id="missing-runtime",
        selected_models=["Naive"],
    )
    report = pd.read_json(run_dir / "VERIFICATION_REPORT.json", typ="series")
    assert report["status"] == "PARTIALLY_VERIFIED"
    package = pd.read_json(run_dir / "PACKAGE_EVIDENCE.json", typ="series")
    assert package["status"] == "DEPENDENCY_MISSING"


def test_version_mismatch_is_not_relabelled_as_missing(tmp_path) -> None:
    run_dir = certify_installed_runtime(
        tmp_path,
        run_id="version-mismatch",
        selected_models=["Naive"],
        injected_version="2.0.3",
    )
    package = pd.read_json(run_dir / "PACKAGE_EVIDENCE.json", typ="series")
    inventory = pd.read_json(run_dir / "RUNTIME_INVENTORY.json", typ="series")
    assert package["status"] == "UNSUPPORTED_BY_VERSION"
    assert inventory["status"] == "UNSUPPORTED_BY_VERSION"
