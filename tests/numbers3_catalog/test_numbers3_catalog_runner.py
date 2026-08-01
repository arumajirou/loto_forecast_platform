from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).parents[2] / "scripts" / "run_numbers3_catalog_models.py"
spec = importlib.util.spec_from_file_location("numbers3_catalog_runner", MODULE_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_load_numbers3_and_worker_conversion(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "draw_no": [2, 1],
            "draw_date": ["2026-01-02", "2026-01-01"],
            "d1": [2, 1],
            "d2": [4, 3],
            "d3": [6, 5],
        }
    )
    path = tmp_path / "numbers3.csv"
    frame.to_csv(path, index=False)
    loaded = runner.load_numbers3(path)
    history = runner.to_worker_history(loaded)
    assert list(history.columns) == ["draw_no", "draw_date", "n1", "n2", "n3"]
    assert history["draw_no"].tolist() == [1, 2]


def test_ridge_position_predicts_three_digits() -> None:
    rows = 80
    frame = pd.DataFrame(
        {
            "draw_no": np.arange(1, rows + 1),
            "draw_date": pd.date_range("2025-01-01", periods=rows, freq="D"),
            "d1": np.arange(rows) % 10,
            "d2": (np.arange(rows) + 3) % 10,
            "d3": (np.arange(rows) + 6) % 10,
        }
    )
    history = runner.to_worker_history(frame)
    args = type(
        "Args",
        (),
        {
            "lags": 5,
            "max_steps": 1,
            "num_samples": 1,
            "hpo_backend": "optuna",
            "device": "cpu",
            "precision": "32",
        },
    )()
    output = runner.predict_worker("ridge-position", history, args, 42)
    assert output.position_values.shape == (3,)
    assert np.all((output.position_values >= 0) & (output.position_values <= 9))


def test_candidate_model_is_not_falsely_mapped() -> None:
    frame = pd.DataFrame(
        {
            "draw_no": range(1, 30),
            "draw_date": pd.date_range("2025-01-01", periods=29, freq="D"),
            "d1": np.arange(29) % 10,
            "d2": np.arange(29) % 10,
            "d3": np.arange(29) % 10,
        }
    )
    args = type(
        "Args",
        (),
        {
            "lags": 5,
            "max_steps": 1,
            "num_samples": 1,
            "hpo_backend": "optuna",
            "device": "cpu",
            "precision": "32",
        },
    )()
    try:
        runner.predict_worker("uniform", runner.to_worker_history(frame), args, 42)
    except NotImplementedError as exc:
        assert "cannot be truthfully mapped" in str(exc)
    else:
        raise AssertionError("candidate model must not be reported as supported")
