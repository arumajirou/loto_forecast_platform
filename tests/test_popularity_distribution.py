from __future__ import annotations

import numpy as np
import pytest

from loto.game.geometry import geometry_for
from loto.strategy.popularity import combination_features
from loto.strategy.popularity_distribution import fit_popularity_count_model


def _synthetic_counts(seed: int = 7) -> tuple[list[list[int]], np.ndarray, np.ndarray]:
    geometry = geometry_for("mini")
    rng = np.random.default_rng(seed)
    universe = np.arange(geometry.value_min, geometry.value_max + 1)
    combinations: list[list[int]] = []
    while len(combinations) < 100:
        values = sorted(rng.choice(universe, size=geometry.positions, replace=False).tolist())
        if values not in combinations:
            combinations.append(values)
    features = np.vstack([combination_features(values, geometry) for values in combinations])
    sales = rng.integers(800_000, 1_200_000, size=len(combinations)).astype(float)
    linear = -11.8 + 0.8 * features[:, 0] - 0.5 * features[:, 3] + 0.6 * features[:, 4]
    mean = sales * np.exp(linear)
    counts = rng.poisson(mean)
    return combinations, counts, sales


@pytest.mark.parametrize("family", ["poisson", "negative_binomial"])
def test_count_popularity_fit_predicts_finite_ordered_uncertainty(family: str) -> None:
    geometry = geometry_for("mini")
    combinations, counts, sales = _synthetic_counts()

    model = fit_popularity_count_model(
        combinations,
        counts,
        geometry,
        sales=sales,
        family=family,
        max_iterations=500,
    )
    selected = combinations[:5]
    selected_sales = sales[:5]
    mean = model.predict_mean(selected, geometry, sales=selected_sales)
    q50 = model.predict_quantile(selected, geometry, sales=selected_sales, q=0.50)
    q80 = model.predict_quantile(selected, geometry, sales=selected_sales, q=0.80)
    q95 = model.predict_quantile(selected, geometry, sales=selected_sales, q=0.95)

    assert np.isfinite(mean).all() and np.all(mean > 0)
    assert np.all(q50 <= q80)
    assert np.all(q80 <= q95)
    assert model.n_observations == len(combinations)
    if family == "negative_binomial":
        assert model.dispersion_alpha is not None and model.dispersion_alpha > 0


def test_prediction_record_never_claims_higher_win_probability_or_actionability() -> None:
    geometry = geometry_for("mini")
    combinations, counts, sales = _synthetic_counts()
    model = fit_popularity_count_model(
        combinations,
        counts,
        geometry,
        sales=sales,
        family="poisson",
    )

    record = model.prediction_record(combinations[0], geometry, sales=float(sales[0]))

    assert record["actionable"] is False
    assert record["win_probability"] == pytest.approx(1.0 / geometry.outcome_space)
    assert record["q50_co_winners"] <= record["q80_co_winners"] <= record["q95_co_winners"]
    assert "not improved" in str(record["win_probability_note"])


def test_count_model_fails_closed_on_bad_sales_counts_and_family() -> None:
    geometry = geometry_for("mini")
    combinations, counts, sales = _synthetic_counts()

    with pytest.raises(ValueError, match="strictly positive"):
        fit_popularity_count_model(
            combinations,
            counts,
            geometry,
            sales=np.zeros_like(sales),
        )
    bad_counts = counts.astype(float)
    bad_counts[0] += 0.5
    with pytest.raises(ValueError, match="integer-valued"):
        fit_popularity_count_model(combinations, bad_counts, geometry, sales=sales)
    with pytest.raises(ValueError, match="unsupported count family"):
        fit_popularity_count_model(
            combinations,
            counts,
            geometry,
            sales=sales,
            family="unsupported",  # type: ignore[arg-type]
        )
