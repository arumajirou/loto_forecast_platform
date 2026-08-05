from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OOFConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_train_size: int = Field(ge=2)
    horizon: int = Field(ge=1)
    step: int = Field(default=1, ge=1)
    max_folds: int | None = Field(default=None, ge=1)
    seeds: tuple[int, ...] = (1, 7, 19)

    @model_validator(mode="after")
    def validate_seeds(self) -> OOFConfig:
        if len(self.seeds) < 2:
            raise ValueError("multi-seed OOF requires at least two seeds")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be unique")
        return self


class TemporalFold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fold_id: int = Field(ge=0)
    train_start: int = Field(ge=0)
    train_end: int = Field(ge=1)
    validation_start: int = Field(ge=1)
    validation_end: int = Field(ge=2)

    @model_validator(mode="after")
    def validate_order(self) -> TemporalFold:
        if self.train_start != 0:
            raise ValueError("expanding-window OOF must start training at row zero")
        if self.train_end != self.validation_start:
            raise ValueError("training and validation must be adjacent and non-overlapping")
        if self.validation_end <= self.validation_start:
            raise ValueError("validation window must contain at least one row")
        return self


class MetricVector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hit_at_1: float = Field(ge=0.0, le=1.0)
    all_positions_hit_at_1: float = Field(ge=0.0, le=1.0)
    mae: float = Field(ge=0.0)
    mse: float = Field(ge=0.0)
    rmse: float = Field(ge=0.0)
    position_hit_at_1: tuple[float, ...] = ()

    @model_validator(mode="after")
    def validate_positions(self) -> MetricVector:
        if any(value < 0.0 or value > 1.0 for value in self.position_hit_at_1):
            raise ValueError("position Hit@±1 values must be in [0, 1]")
        return self


class SeedFoldResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    seed: int
    fold_id: int = Field(ge=0)
    metrics: MetricVector


class ScalarSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mean: float
    variance: float = Field(ge=0.0)
    worst: float


class SeedSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int
    fold_ids: tuple[int, ...]
    metrics: MetricVector


class CandidateAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    seeds: tuple[int, ...]
    fold_ids: tuple[int, ...]
    seed_summaries: tuple[SeedSummary, ...]
    hit_at_1: ScalarSummary
    all_positions_hit_at_1: ScalarSummary
    mae: ScalarSummary
    mse: ScalarSummary
    rmse: ScalarSummary
    position_hit_at_1: tuple[ScalarSummary, ...]


class BaselineComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    baseline_id: str
    mean_hit_delta: float
    worst_hit_delta: float
    mean_mae_delta: float
    beats_primary_baseline: bool


class ChampionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    champion_id: str | None
    status: str
    reason: str
    ranking: tuple[str, ...]
    comparisons: tuple[BaselineComparison, ...]


Evaluator = Callable[[pd.DataFrame, pd.DataFrame, int, TemporalFold], MetricVector]


def build_expanding_folds(n_rows: int, config: OOFConfig) -> tuple[TemporalFold, ...]:
    if n_rows < config.min_train_size + config.horizon:
        raise ValueError("not enough rows for one chronological OOF fold")
    folds: list[TemporalFold] = []
    train_end = config.min_train_size
    while train_end + config.horizon <= n_rows:
        folds.append(
            TemporalFold(
                fold_id=len(folds),
                train_start=0,
                train_end=train_end,
                validation_start=train_end,
                validation_end=train_end + config.horizon,
            )
        )
        train_end += config.step
    if config.max_folds is not None and len(folds) > config.max_folds:
        selected = folds[-config.max_folds :]
        folds = [fold.model_copy(update={"fold_id": index}) for index, fold in enumerate(selected)]
    return tuple(folds)


def run_oof(
    frame: pd.DataFrame,
    config: OOFConfig,
    evaluators: Mapping[str, Evaluator],
) -> tuple[SeedFoldResult, ...]:
    if not evaluators:
        raise ValueError("at least one candidate or baseline evaluator is required")
    original = frame.copy(deep=True)
    folds = build_expanding_folds(len(frame), config)
    results: list[SeedFoldResult] = []
    for candidate_id in sorted(evaluators):
        evaluator = evaluators[candidate_id]
        for seed in config.seeds:
            for fold in folds:
                train = frame.iloc[fold.train_start : fold.train_end].copy(deep=True)
                validation = frame.iloc[
                    fold.validation_start : fold.validation_end
                ].copy(deep=True)
                metrics = evaluator(train, validation, seed, fold)
                results.append(
                    SeedFoldResult(
                        candidate_id=candidate_id,
                        seed=seed,
                        fold_id=fold.fold_id,
                        metrics=metrics,
                    )
                )
    pd.testing.assert_frame_equal(frame, original, check_exact=True)
    return tuple(results)


def _metric_mean(records: Sequence[SeedFoldResult], name: str) -> float:
    values = [float(getattr(record.metrics, name)) for record in records]
    return float(np.mean(values))


def _position_means(records: Sequence[SeedFoldResult]) -> tuple[float, ...]:
    widths = {len(record.metrics.position_hit_at_1) for record in records}
    if len(widths) != 1:
        raise ValueError("position metric width must match across folds and seeds")
    width = widths.pop()
    return tuple(
        float(np.mean([record.metrics.position_hit_at_1[index] for record in records]))
        for index in range(width)
    )


def _scalar_summary(values: Sequence[float], *, higher_is_better: bool) -> ScalarSummary:
    array = np.asarray(values, dtype=float)
    worst = float(np.min(array) if higher_is_better else np.max(array))
    return ScalarSummary(
        mean=float(np.mean(array)),
        variance=float(np.var(array, ddof=0)),
        worst=worst,
    )


def aggregate_candidate(records: Sequence[SeedFoldResult]) -> CandidateAggregate:
    if not records:
        raise ValueError("candidate records must not be empty")
    candidate_ids = {record.candidate_id for record in records}
    if len(candidate_ids) != 1:
        raise ValueError("aggregate_candidate accepts exactly one candidate")

    grouped: dict[int, list[SeedFoldResult]] = defaultdict(list)
    seen: set[tuple[int, int]] = set()
    for record in records:
        key = (record.seed, record.fold_id)
        if key in seen:
            raise ValueError(f"duplicate seed/fold result: {key}")
        seen.add(key)
        grouped[record.seed].append(record)
    if len(grouped) < 2:
        raise ValueError("candidate adoption cannot rely on a single seed")

    expected_folds: tuple[int, ...] | None = None
    seed_summaries: list[SeedSummary] = []
    for seed in sorted(grouped):
        seed_records = sorted(grouped[seed], key=lambda record: record.fold_id)
        fold_ids = tuple(record.fold_id for record in seed_records)
        if expected_folds is None:
            expected_folds = fold_ids
        elif fold_ids != expected_folds:
            raise ValueError("every seed must cover the same OOF folds")
        seed_summaries.append(
            SeedSummary(
                seed=seed,
                fold_ids=fold_ids,
                metrics=MetricVector(
                    hit_at_1=_metric_mean(seed_records, "hit_at_1"),
                    all_positions_hit_at_1=_metric_mean(
                        seed_records, "all_positions_hit_at_1"
                    ),
                    mae=_metric_mean(seed_records, "mae"),
                    mse=_metric_mean(seed_records, "mse"),
                    rmse=_metric_mean(seed_records, "rmse"),
                    position_hit_at_1=_position_means(seed_records),
                ),
            )
        )

    assert expected_folds is not None
    hit_values = [summary.metrics.hit_at_1 for summary in seed_summaries]
    all_hit_values = [summary.metrics.all_positions_hit_at_1 for summary in seed_summaries]
    mae_values = [summary.metrics.mae for summary in seed_summaries]
    mse_values = [summary.metrics.mse for summary in seed_summaries]
    rmse_values = [summary.metrics.rmse for summary in seed_summaries]
    position_width = len(seed_summaries[0].metrics.position_hit_at_1)
    position_summaries = tuple(
        _scalar_summary(
            [summary.metrics.position_hit_at_1[index] for summary in seed_summaries],
            higher_is_better=True,
        )
        for index in range(position_width)
    )
    return CandidateAggregate(
        candidate_id=next(iter(candidate_ids)),
        seeds=tuple(summary.seed for summary in seed_summaries),
        fold_ids=expected_folds,
        seed_summaries=tuple(seed_summaries),
        hit_at_1=_scalar_summary(hit_values, higher_is_better=True),
        all_positions_hit_at_1=_scalar_summary(all_hit_values, higher_is_better=True),
        mae=_scalar_summary(mae_values, higher_is_better=False),
        mse=_scalar_summary(mse_values, higher_is_better=False),
        rmse=_scalar_summary(rmse_values, higher_is_better=False),
        position_hit_at_1=position_summaries,
    )


def aggregate_all(records: Sequence[SeedFoldResult]) -> tuple[CandidateAggregate, ...]:
    grouped: dict[str, list[SeedFoldResult]] = defaultdict(list)
    for record in records:
        grouped[record.candidate_id].append(record)
    return tuple(aggregate_candidate(grouped[candidate_id]) for candidate_id in sorted(grouped))


def rank_candidates(candidates: Sequence[CandidateAggregate]) -> tuple[CandidateAggregate, ...]:
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.hit_at_1.mean,
                -candidate.hit_at_1.worst,
                -candidate.all_positions_hit_at_1.mean,
                candidate.mae.mean,
                candidate.candidate_id,
            ),
        )
    )


def compare_to_baseline(
    candidate: CandidateAggregate,
    baseline: CandidateAggregate,
) -> BaselineComparison:
    if candidate.seeds != baseline.seeds or candidate.fold_ids != baseline.fold_ids:
        raise ValueError("candidate and baseline must share seeds and OOF folds")
    mean_hit_delta = candidate.hit_at_1.mean - baseline.hit_at_1.mean
    worst_hit_delta = candidate.hit_at_1.worst - baseline.hit_at_1.worst
    mean_mae_delta = candidate.mae.mean - baseline.mae.mean
    return BaselineComparison(
        candidate_id=candidate.candidate_id,
        baseline_id=baseline.candidate_id,
        mean_hit_delta=mean_hit_delta,
        worst_hit_delta=worst_hit_delta,
        mean_mae_delta=mean_mae_delta,
        beats_primary_baseline=(mean_hit_delta > 0.0 and worst_hit_delta >= 0.0),
    )


def select_champion(
    candidates: Sequence[CandidateAggregate],
    baseline: CandidateAggregate,
) -> ChampionDecision:
    ranked = rank_candidates(candidates)
    comparisons = tuple(compare_to_baseline(candidate, baseline) for candidate in ranked)
    for comparison in comparisons:
        if comparison.beats_primary_baseline:
            return ChampionDecision(
                champion_id=comparison.candidate_id,
                status="PROPOSED",
                reason=(
                    "mean Hit@±1 improved and worst-seed Hit@±1 did not regress "
                    "against the declared baseline"
                ),
                ranking=tuple(candidate.candidate_id for candidate in ranked),
                comparisons=comparisons,
            )
    return ChampionDecision(
        champion_id=None,
        status="NO_CHAMPION",
        reason="no candidate passed the mean and worst-seed Hit@±1 baseline gate",
        ranking=tuple(candidate.candidate_id for candidate in ranked),
        comparisons=comparisons,
    )
