from __future__ import annotations

import numpy as np
import pytest

from loto.auto_campaign.prospective_baselines import (
    BASELINE_NAMES,
    generate_prospective_baselines,
)


def _history() -> np.ndarray:
    return np.asarray(
        [
            [1, 5, 10, 20, 28],
            [2, 6, 11, 21, 29],
            [3, 7, 12, 22, 30],
            [4, 8, 13, 23, 31],
        ],
        dtype=float,
    )


def test_all_required_baselines_are_finite_and_deterministic() -> None:
    first, metadata = generate_prospective_baselines(
        _history(),
        horizon=2,
        random_seed=1,
    )
    second, _ = generate_prospective_baselines(
        _history(),
        horizon=2,
        random_seed=1,
    )

    assert tuple(first) == BASELINE_NAMES
    assert metadata["history_rows"] == 4
    assert metadata["horizon"] == 2
    assert metadata["random_seed"] == 1
    for name, values in first.items():
        assert values.shape == (2, 5)
        assert np.isfinite(values).all()
        np.testing.assert_array_equal(values, second[name])


def test_random_seed_changes_only_random_baseline() -> None:
    first, _ = generate_prospective_baselines(_history(), horizon=1, random_seed=1)
    second, _ = generate_prospective_baselines(_history(), horizon=1, random_seed=2)

    assert not np.array_equal(first["random_uniform"], second["random_uniform"])
    for name in set(BASELINE_NAMES) - {"random_uniform"}:
        np.testing.assert_allclose(first[name], second[name])


def test_constant_series_records_statistical_fallback() -> None:
    history = np.repeat(np.asarray([[1, 5, 10, 20, 28]], dtype=float), 4, axis=0)

    baselines, metadata = generate_prospective_baselines(history, horizon=2)

    assert metadata["statistical_fallback_positions"] == [1, 2, 3, 4, 5]
    np.testing.assert_allclose(
        baselines["statistical_ar1"],
        np.repeat(history[-1:].copy(), 2, axis=0),
    )


@pytest.mark.parametrize(
    "history,horizon",
    [
        (np.asarray([1, 2, 3], dtype=float), 1),
        (np.asarray([[1, 2, 3, 4, np.nan]] * 3), 1),
        (np.asarray([[1, 2, 3, 4, 5]] * 3), 0),
    ],
)
def test_invalid_baseline_inputs_are_rejected(
    history: np.ndarray,
    horizon: int,
) -> None:
    with pytest.raises(ValueError):
        generate_prospective_baselines(history, horizon=horizon)
