from __future__ import annotations

import pandas as pd
import pytest

from loto.darts_campaign.campaign import (
    MetricVector,
    OOFConfig,
    SeedFoldResult,
    aggregate_all,
    build_expanding_folds,
    run_oof,
    select_champion,
)


def _metric(hit: float, mae: float) -> MetricVector:
    return MetricVector(
        hit_at_1=hit,
        all_positions_hit_at_1=max(0.0, hit - 0.1),
        mae=mae,
        mse=mae**2,
        rmse=mae,
        position_hit_at_1=(hit, hit),
    )


def test_expanding_folds_are_time_ordered_and_non_overlapping() -> None:
    config = OOFConfig(min_train_size=5, horizon=2, step=2, max_folds=2, seeds=(1, 7))
    folds = build_expanding_folds(12, config)
    assert [(fold.train_end, fold.validation_start, fold.validation_end) for fold in folds] == [
        (7, 7, 9),
        (9, 9, 11),
    ]


def test_run_oof_preserves_input_and_covers_every_seed_fold() -> None:
    frame = pd.DataFrame({"draw_no": range(1, 11), "n1": range(10)})
    original = frame.copy(deep=True)
    seen: list[tuple[int, int, int]] = []

    def evaluator(train, validation, seed, fold):
        seen.append((seed, len(train), len(validation)))
        train.iloc[0, 0] = -999
        return _metric(0.5, 1.0)

    config = OOFConfig(min_train_size=6, horizon=2, step=2, seeds=(1, 7))
    results = run_oof(frame, config, {"candidate": evaluator})
    pd.testing.assert_frame_equal(frame, original, check_exact=True)
    assert len(results) == 4
    assert seen == [(1, 6, 2), (1, 8, 2), (7, 6, 2), (7, 8, 2)]


def test_aggregate_rejects_single_seed_and_inconsistent_fold_coverage() -> None:
    single_seed = [SeedFoldResult(candidate_id="x", seed=1, fold_id=0, metrics=_metric(0.5, 1.0))]
    with pytest.raises(ValueError, match="single seed"):
        aggregate_all(single_seed)

    inconsistent = [
        SeedFoldResult(candidate_id="x", seed=1, fold_id=0, metrics=_metric(0.5, 1.0)),
        SeedFoldResult(candidate_id="x", seed=7, fold_id=1, metrics=_metric(0.5, 1.0)),
    ]
    with pytest.raises(ValueError, match="same OOF folds"):
        aggregate_all(inconsistent)


def test_champion_uses_seed_mean_and_worst_not_best_seed() -> None:
    records: list[SeedFoldResult] = []
    values = {
        "unstable": {1: (1.0, 0.1), 7: (0.2, 2.0)},
        "stable": {1: (0.7, 0.8), 7: (0.7, 0.8)},
        "baseline:last": {1: (0.6, 1.0), 7: (0.6, 1.0)},
    }
    for candidate_id, seed_values in values.items():
        for seed, (hit, mae) in seed_values.items():
            for fold_id in (0, 1):
                records.append(
                    SeedFoldResult(
                        candidate_id=candidate_id,
                        seed=seed,
                        fold_id=fold_id,
                        metrics=_metric(hit, mae),
                    )
                )
    aggregates = {item.candidate_id: item for item in aggregate_all(records)}
    decision = select_champion(
        [aggregates["unstable"], aggregates["stable"]],
        aggregates["baseline:last"],
    )
    assert decision.champion_id == "stable"
    assert decision.ranking == ("stable", "unstable")
    assert aggregates["unstable"].hit_at_1.worst == pytest.approx(0.2)
    assert aggregates["stable"].hit_at_1.variance == pytest.approx(0.0)
