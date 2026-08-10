from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from loto.adapters.timer_base_84m.contracts import (
    TimerRequest,
    TimerResponse,
)
from loto.timer_base_84m_campaign.oof import (
    DevelopmentSnapshotReader,
    TimerPredictionSpec,
    run_baseline_target_bundle,
    run_timer_target_bundle,
    verify_target_bundle,
)


def _write_numbers3_snapshot(
    root: Path,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "game_id":
                ["numbers3"] * 130,
            "draw_no":
                list(range(1, 131)),
            "ds":
                pd.date_range(
                    "2025-01-01",
                    periods=130,
                    freq="D",
                ),
            "N1":
                [
                    value % 10
                    for value in range(130)
                ],
            "N2":
                [
                    (value + 3) % 10
                    for value in range(130)
                ],
            "N3":
                [
                    (value + 6) % 10
                    for value in range(130)
                ],
        }
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame.to_parquet(
        root / "numbers3.parquet",
        index=False,
        engine="pyarrow",
    )

    return frame


def _fake_predictor(
    request: TimerRequest,
) -> TimerResponse:
    prediction = tuple(
        (
            float(values[-1]) + 0.25,
        )
        for values in request.series
    )

    input_raw = np.asarray(
        request.series,
        dtype="<f4",
    ).tobytes()

    prediction_raw = np.asarray(
        prediction,
        dtype="<f4",
    ).tobytes()

    return TimerResponse(
        schema_version=
            "timer-base-84m.response.v1",
        run_id=request.run_id,
        status="PREDICTED",
        model_id=request.model_id,
        repo_id=request.repo_id,
        package_version=
            request.package_version,
        source_revision=
            request.source_revision,
        observed_source_head=
            request.observed_source_head,
        model_revision=
            request.model_revision,
        config_sha256=
            request.config_sha256,
        weight_sha256=
            request.weight_sha256,
        license=request.license,
        game=request.game,
        target_layout=
            request.target_layout,
        context_length=
            request.context_length,
        prediction_length=
            request.prediction_length,
        seed=request.seed,
        requested_device=
            request.requested_device,
        effective_device="cpu",
        cpu_fallback=False,
        input_shape=request.input_shape,
        output_shape=(
            len(request.series),
            1,
        ),
        point_forecast=prediction,
        quantiles=None,
        samples=None,
        finite_check=True,
        chronology_evidence=
            request.chronology_evidence,
        actuals_used=False,
        runtime_pid=123,
        gpu_uuid=None,
        gpu_process_vram_bytes=None,
        input_series_sha256_f32=
            hashlib.sha256(
                input_raw
            ).hexdigest(),
        prediction_sha256_f32=
            hashlib.sha256(
                prediction_raw
            ).hexdigest(),
        chronology_mapping_sha256=
            request.chronology_evidence
            .mapping_sha256,
        artifact_paths=
            request.artifact_paths,
    )


def test_context_reader_excludes_target_actual(
    tmp_path,
) -> None:
    snapshot = tmp_path / "snapshot"
    _write_numbers3_snapshot(
        snapshot
    )

    reader = DevelopmentSnapshotReader(
        snapshot
    )

    context = reader.read_context(
        game_id="numbers3",
        target_draw_no=121,
        context_length=96,
    )

    assert context[
        "draw_no"
    ].tolist() == list(
        range(25, 121)
    )

    assert 121 not in set(
        context["draw_no"]
    )


def test_baseline_bundle_seals_all_predictions_before_actual(
    tmp_path,
) -> None:
    snapshot = tmp_path / "snapshot"
    frame = _write_numbers3_snapshot(
        snapshot
    )

    target_ds = pd.Timestamp(
        frame.loc[
            frame["draw_no"] == 121,
            "ds",
        ].iloc[0]
    ).date()

    reader = DevelopmentSnapshotReader(
        snapshot
    )

    result = run_baseline_target_bundle(
        reader=reader,
        output_dir=(
            tmp_path
            / "baseline-target"
        ),
        run_id="baseline-test-run",
        game_id="numbers3",
        target_draw_no=121,
        target_ds=target_ds,
        context_length=96,
        seeds=(
            42,
            1729,
            20260730,
        ),
    )

    verify_target_bundle(
        result
    )

    assert len(
        result.seals
    ) == 9

    assert all(
        sealed.sealed_at_utc
        <= result.actual_reveal.actual_read_at_utc
        for sealed in result.seals
    )

    score = json.loads(
        result.score_path.read_text(
            encoding="utf-8"
        )
    )

    assert score[
        "all_predictions_sealed_before_actual"
    ] is True

    assert len(
        score["scores"]
    ) == 9

    for item in score["scores"]:
        assert set(
            item["metrics"]
        ) == {
            "hit_at_1",
            "position_hit_at_1",
            "all_positions_hit_at_1",
            "mae",
            "mse",
            "rmse",
        }


def test_timer_bundle_seals_layouts_before_actual(
    tmp_path,
) -> None:
    snapshot = tmp_path / "snapshot"
    frame = _write_numbers3_snapshot(
        snapshot
    )

    target_ds: date = pd.Timestamp(
        frame.loc[
            frame["draw_no"] == 121,
            "ds",
        ].iloc[0]
    ).date()

    reader = DevelopmentSnapshotReader(
        snapshot
    )

    result = run_timer_target_bundle(
        reader=reader,
        output_dir=(
            tmp_path
            / "timer-target"
        ),
        run_id="timer-test-run",
        game_id="numbers3",
        target_draw_no=121,
        target_ds=target_ds,
        context_length=96,
        specs=(
            TimerPredictionSpec(
                candidate_id=
                    "timer-position-univariate",
                target_layout=
                    "position_univariate",
                seed=42,
                requested_device="cpu",
            ),
            TimerPredictionSpec(
                candidate_id=
                    "timer-position-panel",
                target_layout=
                    "position_panel_batched_univariate",
                seed=1729,
                requested_device="cpu",
            ),
        ),
        predictor=_fake_predictor,
    )

    verify_target_bundle(
        result
    )

    assert len(
        result.seals
    ) == 2

    assert all(
        sealed.sealed_at_utc
        <= result.actual_reveal.actual_read_at_utc
        for sealed in result.seals
    )

    score = json.loads(
        result.score_path.read_text(
            encoding="utf-8"
        )
    )

    assert score[
        "all_predictions_sealed_before_actual"
    ] is True

    assert {
        item["target_layout"]
        for item in score["scores"]
    } == {
        "position_univariate",
        "position_panel_batched_univariate",
    }
