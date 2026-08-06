from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loto.orchestration.pipeline_ledger import (
    PipelineDatasetEvidence,
    PipelineLedgerBlocked,
    PipelineLedgerRecorder,
)
from loto.orchestration.pipeline_staged_support import (
    EXPECTED_PIPELINE_BLOB_SHA,
    PipelineComponents,
    RecorderFactory,
    StagedPipelineBlocked,
    StagedPipelineError,
    StagedPipelinePreflightError,
    _absolute,
    _atomic_write_json,
    _candidate_targets,
    _default_components,
    _manifest_value,
    _metric_bundle,
    _model_dump,
    _reject_symlink_components,
    _require_empty_output,
    _require_regular_file,
    _utc,
    file_sha256,
    git_blob_sha,
)


def run_trusted_vertical_slice_staged(
    input_csv: str | Path,
    output_dir: str | Path,
    *,
    secret: bytes,
    backtest_draws: int = 20,
    windows: tuple[int, ...] = (10, 30, 100),
    seed: int = 0,
    pipeline_source: Path | None = None,
    expected_pipeline_blob_sha: str = EXPECTED_PIPELINE_BLOB_SHA,
    components: PipelineComponents | None = None,
    recorder_factory: RecorderFactory = PipelineLedgerRecorder,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Compute and seal the trusted vertical slice before downstream registration.

    Registry, PlatformRegistry, MLflow, release-bundle publication, and ArtifactStore
    writes are intentionally not executed. A successful return means only that local
    computation and Data Access Ledger validation are ready for a later commit phase.
    """

    if not isinstance(secret, bytes) or len(secret) < 16:
        raise StagedPipelinePreflightError("secret must contain at least 16 bytes")
    if backtest_draws < 1:
        raise StagedPipelinePreflightError("backtest_draws must be >= 1")
    if not windows or any(window < 1 for window in windows):
        raise StagedPipelinePreflightError("feature windows must be positive")

    source = _absolute(Path(input_csv))
    output = _absolute(Path(output_dir))
    _require_regular_file(source, label="input")
    _reject_symlink_components(output, label="output")

    root = Path(__file__).resolve().parents[3]
    audited_source = pipeline_source or root / "src/loto/orchestration/pipeline.py"
    audited_source = _absolute(audited_source)
    _require_regular_file(audited_source, label="legacy pipeline source")
    observed_blob = git_blob_sha(audited_source)
    if observed_blob != expected_pipeline_blob_sha:
        raise StagedPipelinePreflightError(
            "legacy pipeline source pin mismatch: "
            f"expected={expected_pipeline_blob_sha} observed={observed_blob}"
        )
    _require_empty_output(output)

    deps = components or _default_components()
    now = clock or (lambda: datetime.now(UTC))
    run_id = f"pipeline-ledger-{uuid.uuid4().hex[:12]}"
    source_sha = file_sha256(source)
    raw = deps.pd.read_csv(source)
    master, manifest = deps.canonicalize_loto7(raw, source=str(source))
    canonical_sha = str(_manifest_value(manifest, "sha256"))
    data_version = str(_manifest_value(manifest, "data_version"))
    observed_times = tuple(
        _utc(value.to_pydatetime() if hasattr(value, "to_pydatetime") else value)
        for value in master["draw_date"].tolist()
    )
    evidence = PipelineDatasetEvidence(
        dataset_id="loto7-canonical",
        canonical_sha256=canonical_sha,
        source_sha256=source_sha,
        data_version=data_version,
        game_id="loto7",
        series_ids=tuple(f"n{index}" for index in range(1, 8)),
        observed_times=observed_times,
        draw_ids=tuple(str(value) for value in master["draw_id"].tolist()),
    )
    recorder = recorder_factory(
        run_id=run_id,
        output_dir=output,
        evidence=evidence,
        seed=seed,
        clock=now,
    )

    resource_evidence = deps.collect_gpu_evidence(gpu_required=False)
    _atomic_write_json(output / "resource_evidence.json", resource_evidence)
    master.to_csv(output / "canonical.csv", index=False)
    deps.save_manifest(manifest, output / "dataset_manifest.json")
    features = deps.build_candidate_features(master, windows=windows)
    feature_info = deps.feature_manifest(features, data_version, windows)
    features.to_csv(output / "candidate_features.csv", index=False)
    _atomic_write_json(output / "feature_manifest.json", _model_dump(feature_info))

    start = max(8, len(master) - max(1, backtest_draws))
    actuals: list[list[int]] = []
    preds_uniform: list[list[int]] = []
    preds_frequency: list[list[int]] = []
    targets: list[Any] = []
    probs_uniform: list[Any] = []
    probs_frequency: list[Any] = []
    per_draw_metrics: list[dict[str, Any]] = []

    for index in range(start, len(master)):
        history = master.iloc[:index]
        test_draw_no = int(master["draw_no"].iloc[index])
        fold_id = f"fold-{test_draw_no}"
        hist_candidates = deps.to_candidate_table(history)
        query = deps.pd.DataFrame({"candidate_number": range(1, 38)})
        predictions: dict[str, tuple[Any, list[int]]] = {}
        for model_id, adapter_type in (
            ("uniform", deps.UniformCandidateAdapter),
            ("frequency", deps.FrequencyCandidateAdapter),
        ):
            recorder.register_oof(model_id=model_id, fold_id=fold_id)
            adapter = adapter_type().fit(hist_candidates)
            prediction = adapter.predict(query)
            position = deps.PositionFrequencyAdapter().fit(history).predict_matrix()
            decoded = deps.decode_hybrid(
                prediction["rank_score"].to_numpy(), position, top_k=1
            )[0].numbers
            recorder.record_oof_prediction(
                model_id=model_id,
                fold_id=fold_id,
                test_index=index,
            )
            predictions[model_id] = (prediction, decoded)

        for model_id in ("uniform", "frequency"):
            recorder.record_oof_actual(
                model_id=model_id,
                fold_id=fold_id,
                test_index=index,
            )
        current = master.iloc[index]
        actual = [int(current[f"n{position}"]) for position in range(1, 8)]
        target = _candidate_targets(actual, deps.np)
        fold_actual = deps.np.asarray([actual])
        fold_target = deps.np.asarray([target])
        for model_id in ("uniform", "frequency"):
            prediction, decoded = predictions[model_id]
            fold_metric = _metric_bundle(
                actual=fold_actual,
                predicted=deps.np.asarray([decoded]),
                targets=fold_target,
                probabilities=deps.np.asarray(
                    [prediction["probability"].to_numpy()]
                ),
                components=deps,
            )
            per_draw_metrics.append(
                {"model_id": model_id, "fold_id": fold_id, **fold_metric}
            )
            recorder.record_oof_score(model_id=model_id, fold_id=fold_id)

        uniform_prediction, uniform_decoded = predictions["uniform"]
        frequency_prediction, frequency_decoded = predictions["frequency"]
        actuals.append(actual)
        targets.append(target)
        preds_uniform.append(uniform_decoded)
        preds_frequency.append(frequency_decoded)
        probs_uniform.append(uniform_prediction["probability"].to_numpy())
        probs_frequency.append(frequency_prediction["probability"].to_numpy())

    if actuals:
        actual_matrix = deps.np.asarray(actuals)
        target_matrix = deps.np.asarray(targets)
        metrics_uniform = _metric_bundle(
            actual=actual_matrix,
            predicted=deps.np.asarray(preds_uniform),
            targets=target_matrix,
            probabilities=deps.np.asarray(probs_uniform),
            components=deps,
        )
        metrics_frequency = _metric_bundle(
            actual=actual_matrix,
            predicted=deps.np.asarray(preds_frequency),
            targets=target_matrix,
            probabilities=deps.np.asarray(probs_frequency),
            components=deps,
        )
    else:
        recorder.mark_gap("BACKTEST_DRAW_EVIDENCE_MISSING")
        metrics_uniform = metrics_frequency = {
            "mean_hits_at_7": 0.0,
            "position_mae": 0.0,
            "position_mse": 0.0,
            "within_1_rate": 0.0,
            "brier": 0.0,
            "log_loss": 0.0,
        }

    champion = (
        "frequency"
        if metrics_frequency["mean_hits_at_7"]
        > metrics_uniform["mean_hits_at_7"]
        and metrics_frequency["brier"] <= metrics_uniform["brier"] * 1.02
        else "uniform"
    )
    report = {
        "uniform": metrics_uniform,
        "frequency": metrics_frequency,
        "champion": champion,
        "backtest_draws": len(actuals),
        "per_draw_metrics": per_draw_metrics,
    }
    _atomic_write_json(output / "evaluation.json", report)

    forecast_id = f"forecast-{uuid.uuid4().hex[:12]}"
    draw_id = f"loto7-{int(master.draw_no.max()) + 1}"
    all_candidates = deps.to_candidate_table(master)
    next_query = deps.build_next_candidate_features(master, windows=windows)
    adapter_type = (
        deps.FrequencyCandidateAdapter
        if champion == "frequency"
        else deps.UniformCandidateAdapter
    )
    model = adapter_type().fit(all_candidates)
    prediction = model.predict(next_query)
    position = deps.PositionFrequencyAdapter().fit(master).predict_matrix()
    combinations = deps.decode_hybrid(
        prediction["rank_score"].to_numpy(), position, top_k=20
    )
    created = _utc(now())
    draw_time = max(
        created + timedelta(minutes=1),
        observed_times[-1] + timedelta(days=7),
    )
    recorder.record_prospective_prediction(
        model_id=champion,
        forecast_id=forecast_id,
        draw_id=draw_id,
        forecast_origin=created,
    )
    forecast = deps.ForecastPackage(
        forecast_id=forecast_id,
        draw_id=draw_id,
        model_id=model.model_id,
        data_version=data_version,
        feature_set_id=str(_manifest_value(feature_info, "feature_set_id")),
        created_at=created,
        draw_time=draw_time,
        combination=combinations[0],
        candidates=[
            deps.CandidateProbability(
                candidate_number=int(row.candidate_number),
                probability=float(row.probability),
                rank_score=float(row.rank_score),
            )
            for row in prediction.itertuples()
        ],
        metadata={
            "run_id": run_id,
            "decoder": "hybrid-dp-v1",
            "champion_selection": champion,
            "pipeline_mode": "STAGED_BEFORE_DOWNSTREAM_COMMIT",
        },
    )
    payload = _model_dump(forecast)
    sealed = deps.seal_payload(payload, secret)
    verified = bool(deps.verify_seal(sealed, secret))
    recorder.record_prediction_lock(forecast_id=forecast_id, verified=verified)
    _atomic_write_json(output / "forecast.json", payload)
    _atomic_write_json(output / "forecast.sealed.json", sealed)

    try:
        ledger_result = recorder.close()
    except PipelineLedgerBlocked as exc:
        raise StagedPipelineBlocked(str(exc)) from exc

    commit_plan = {
        "status": "READY_FOR_DOWNSTREAM_COMMIT",
        "run_id": run_id,
        "ledger_sha256": ledger_result.ledger_sha256,
        "executed": False,
        "deferred_operations": [
            "Registry.record_stage",
            "Registry.record_forecast",
            "PlatformRegistry.create_run/update_run/register_forecast/register_model",
            "MlflowBridge.record_run",
            "create_release_bundle",
            "ArtifactStore.put_file",
            "EventPublisher.publish",
        ],
        "reason": (
            "Downstream persistence is intentionally separated from Data Access "
            "Ledger computation and validation."
        ),
    }
    _atomic_write_json(output / "downstream_commit_plan.json", commit_plan)
    return {
        "run_id": run_id,
        "status": "READY_FOR_DOWNSTREAM_COMMIT",
        "forecast": payload,
        "seal_verified": verified,
        "evaluation": report,
        "data_access_ledger": str(ledger_result.ledger_path),
        "data_access_validation": str(ledger_result.validation_path),
        "data_access_ledger_sha256": ledger_result.ledger_sha256,
        "downstream_commit_plan": str(output / "downstream_commit_plan.json"),
        "output_dir": str(output),
    }


__all__ = [
    "EXPECTED_PIPELINE_BLOB_SHA",
    "PipelineComponents",
    "StagedPipelineBlocked",
    "StagedPipelineError",
    "StagedPipelinePreflightError",
    "file_sha256",
    "git_blob_sha",
    "run_trusted_vertical_slice_staged",
]
