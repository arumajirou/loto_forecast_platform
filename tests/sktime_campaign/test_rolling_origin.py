from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from loto.sktime_campaign.benchmark import BaselineId, ChronologicalSplit, GameMatrix
from loto.sktime_campaign.rolling_artifacts import (
    P3VerificationError,
    persist_p3,
    verify_p3,
)
from loto.sktime_campaign.rolling_origin import (
    RollingOriginRequest,
    RollingOriginSpec,
    aggregate_oof_results,
    build_oof_leaderboard,
    build_rolling_folds,
    run_p3,
    verify_prediction_lock,
)


def _dataset(*, mutate_holdout: bool = False) -> GameMatrix:
    values = [[float((row + col) % 10) for col in range(2)] for row in range(30)]
    if mutate_holdout:
        values[-5:] = [
            [9.0, 0.0],
            [8.0, 1.0],
            [7.0, 2.0],
            [6.0, 3.0],
            [5.0, 4.0],
        ]
    return GameMatrix(
        game_id="numbers3-contract",
        draw_no=list(range(1, 31)),
        position_names=["N1", "N2"],
        values=values,
        legal_min=[0, 0],
        legal_max=[9, 9],
    )


def _request(tmp_path: Path, *, mutate_holdout: bool = False) -> RollingOriginRequest:
    return RollingOriginRequest(
        output_dir=str(tmp_path / "p3"),
        run_id="p3-test",
        git_commit="abcdef1",
        code_sha256="1" * 64,
        config_sha256="2" * 64,
        validation_artifact_sha256="3" * 64,
        dataset=_dataset(mutate_holdout=mutate_holdout),
        split=ChronologicalSplit(train_rows=21, validation_rows=4, holdout_rows=5),
        rolling_origin=RollingOriginSpec(
            initial_train_rows=9,
            fold_horizon=3,
            step_length=3,
            minimum_folds=4,
        ),
        baseline_ids=list(BaselineId),
        model_ids=[],
        random_seeds=[1, 2, 3],
        season_length=7,
    )


def test_rolling_folds_stay_inside_train(tmp_path: Path) -> None:
    folds = build_rolling_folds(_request(tmp_path))
    assert len(folds) == 4
    assert [(row["train_end"], row["test_start"], row["test_end"]) for row in folds] == [
        (9, 9, 12),
        (12, 12, 15),
        (15, 15, 18),
        (18, 18, 21),
    ]
    assert max(row["test_end"] for row in folds) == 21


def test_request_rejects_too_few_folds(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RollingOriginRequest(
            **{
                **_request(tmp_path).model_dump(),
                "rolling_origin": {
                    "initial_train_rows": 18,
                    "fold_horizon": 3,
                    "step_length": 3,
                    "minimum_folds": 2,
                },
            }
        )


def test_oof_and_lock_cover_all_baseline_seeds(tmp_path: Path) -> None:
    result = run_p3(_request(tmp_path), sealed_at_utc="2026-08-05T07:00:00Z")
    assert result["status"] == "PASS"
    assert len(result["folds"]) == 4
    assert len(result["oof_results"]) == 36
    assert len(result["holdout_prediction_lock"]["prediction_rows"]) == 9
    assert all(row["fit_scope"] == "OOF_TRAIN_PREFIX_ONLY" for row in result["oof_results"])
    assert all("metrics" in row for row in result["oof_results"])


def test_seed_aggregation_retains_mean_variance_and_worst(tmp_path: Path) -> None:
    result = run_p3(_request(tmp_path), sealed_at_utc="2026-08-05T07:00:00Z")
    seed_metrics, aggregates = aggregate_oof_results(result["oof_results"])
    random_seeds = [row for row in seed_metrics if row["candidate_id"] == "random_uniform"]
    assert [row["seed"] for row in random_seeds] == [1, 2, 3]
    random_aggregate = next(row for row in aggregates if row["candidate_id"] == "random_uniform")
    assert random_aggregate["seed_count"] == 3
    assert set(random_aggregate["metrics"]["hit_at_1"]) == {
        "mean",
        "variance",
        "worst",
    }
    assert build_oof_leaderboard(aggregates)


def test_holdout_actual_mutation_does_not_change_prediction_lock(tmp_path: Path) -> None:
    first = run_p3(
        _request(tmp_path / "first"),
        sealed_at_utc="2026-08-05T07:00:00Z",
    )["holdout_prediction_lock"]
    second = run_p3(
        _request(tmp_path / "second", mutate_holdout=True),
        sealed_at_utc="2026-08-05T07:00:00Z",
    )["holdout_prediction_lock"]
    assert first == second


def test_prediction_lock_rejects_tampering(tmp_path: Path) -> None:
    lock = run_p3(
        _request(tmp_path),
        sealed_at_utc="2026-08-05T07:00:00Z",
    )["holdout_prediction_lock"]
    verify_prediction_lock(lock)
    tampered = deepcopy(lock)
    tampered["prediction_rows"][0]["predictions"][0][0] += 1
    with pytest.raises(ValueError, match="SHA-256"):
        verify_prediction_lock(tampered)


def test_persist_and_verify_p3_bundle(tmp_path: Path) -> None:
    request = _request(tmp_path)
    response = persist_p3(request, sealed_at_utc="2026-08-05T07:00:00Z")
    assert response["status"] == "PASS"
    report = verify_p3(Path(request.output_dir), request, formal=False)
    assert report["status"] == "PASS"
    assert report["fold_count"] == 4
    assert report["locked_prediction_count"] == 9


def test_verifier_detects_prediction_lock_mutation(tmp_path: Path) -> None:
    request = _request(tmp_path)
    persist_p3(request, sealed_at_utc="2026-08-05T07:00:00Z")
    path = Path(request.output_dir) / "HOLDOUT_PREDICTION_LOCK.json"
    text = path.read_text(encoding="utf-8")
    changed = text.replace(
        '"actuals_known": false',
        '"actuals_known": true',
        1,
    )
    path.write_text(changed, encoding="utf-8")
    with pytest.raises(P3VerificationError):
        verify_p3(Path(request.output_dir), request, formal=False)


def test_prediction_lock_rejects_invalid_timestamp(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timestamp"):
        run_p3(
            _request(tmp_path),
            sealed_at_utc="not-a-time",
        )


def test_verifier_rejects_missing_oof_candidate_seed(tmp_path: Path) -> None:
    request = _request(tmp_path)
    persist_p3(request, sealed_at_utc="2026-08-05T07:00:00Z")
    path = Path(request.output_dir) / "OOF_RESULTS.json"
    import json

    rows = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(rows[:-1]), encoding="utf-8")
    with pytest.raises(P3VerificationError, match="inventory"):
        verify_p3(Path(request.output_dir), request, formal=False)


def test_formal_verifier_rejects_reduced_inventory(tmp_path: Path) -> None:
    request = _request(tmp_path)
    persist_p3(request, sealed_at_utc="2026-08-05T07:00:00Z")
    with pytest.raises(P3VerificationError, match="model inventory"):
        verify_p3(Path(request.output_dir), request, formal=True)


def test_all_unavailable_models_remain_unavailable(tmp_path: Path) -> None:
    from loto.sktime_campaign.protocol import SmokeModelId

    payload = _request(tmp_path).model_dump()
    payload["baseline_ids"] = []
    payload["model_ids"] = [SmokeModelId.NAIVE_LAST]
    request = RollingOriginRequest.model_validate(payload)

    def unavailable_predictor(model_id, train, horizon, active_request):
        del model_id, train, horizon, active_request
        return {
            "candidate_id": "naive_last",
            "candidate_kind": "sktime",
            "status": "UNAVAILABLE",
        }

    result = run_p3(
        request,
        sealed_at_utc="2026-08-05T07:00:00Z",
        model_predictor=unavailable_predictor,
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["oof_candidate_aggregates"][0]["status"] == "UNAVAILABLE"
