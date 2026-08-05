from __future__ import annotations

from pathlib import Path

import numpy as np

from loto.toto2_campaign.replay import compare_native_outputs


def _save(path: Path, values: np.ndarray) -> None:
    with path.open("wb") as handle:
        np.save(handle, values, allow_pickle=False)


def test_compare_native_outputs_requires_exact_equality(tmp_path: Path) -> None:
    first = tmp_path / "first.npy"
    second = tmp_path / "second.npy"
    values = np.arange(18, dtype=np.float32).reshape(9, 1, 2, 1)
    _save(first, values)
    _save(second, values.copy())
    result = compare_native_outputs(first, second)
    assert result["exact_equal"] is True
    assert result["first_sha256"] == result["second_sha256"]
    assert result["max_abs_diff"] == 0.0


def test_compare_native_outputs_reports_drift(tmp_path: Path) -> None:
    first = tmp_path / "first.npy"
    second = tmp_path / "second.npy"
    values = np.arange(9, dtype=np.float32).reshape(9, 1, 1, 1)
    changed = values.copy()
    changed[-1, 0, 0, 0] += 0.25
    _save(first, values)
    _save(second, changed)
    result = compare_native_outputs(first, second)
    assert result["exact_equal"] is False
    assert result["max_abs_diff"] == 0.25
