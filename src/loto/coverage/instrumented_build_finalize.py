from __future__ import annotations

from typing import Any

from loto.coverage.ledger import atomic_write_json


def finalize_build(**ctx: Any) -> dict[str, Any]:
    raw = ctx["raw"]
    runner = ctx["runner"]
    pd = ctx["pd"]
    np = ctx["np"]
    output = ctx["output"]
    data = ctx["data"]
    methods = ctx["methods"]
    cal_actual = ctx["cal_actual"]
    cal_pred = ctx["cal_pred"]
    cfg = runner.CoverageConfig(**raw.get("coverage", {}))
    radius = runner.simultaneous_conformal_radius(
        cal_actual,
        cal_pred,
        cfg.target_coverage + cfg.calibration_margin,
    )
    center = runner._point_forecast(data, "median")
    method_centers = np.vstack(
        [runner._point_forecast(data, method) for method in methods]
    )
    ensemble_center = np.rint(np.median(method_centers, axis=0)).astype(int)
    residuals = cal_actual - cal_pred
    probabilities = runner.position_probabilities(data, ensemble_center)
    pool = runner.generate_candidate_pool(
        probabilities,
        per_position_top=cfg.per_position_top,
        beam_width=cfg.beam_width,
        pool_size=cfg.pool_size,
    )
    pool.extend(
        runner.augment_with_residual_offsets(
            ensemble_center,
            residuals,
            radius=max(1, min(radius, 3)),
            limit=cfg.pool_size,
        )
    )
    pool.extend([tuple(center.tolist()), tuple(ensemble_center.tolist())])
    pool = list(dict.fromkeys(pool))[: cfg.pool_size]
    selected, trace = runner.greedy_coverage_select(
        cal_actual,
        pool,
        target_coverage=min(1.0, cfg.target_coverage + cfg.calibration_margin),
        tolerance=cfg.tolerance,
        max_candidates=cfg.max_candidates,
        diversity_penalty=cfg.diversity_penalty,
    )
    calibration_eval = runner.evaluate_candidates(
        cal_actual, selected, cfg.tolerance
    )
    validation_eval = runner.evaluate_candidates(
        ctx["val_actual"], selected, cfg.tolerance
    )
    prediction_set = runner.PredictionSet(
        candidates=selected,
        target_coverage=cfg.target_coverage,
        calibration_coverage=calibration_eval.row_within_tolerance,
        tolerance=cfg.tolerance,
        conformal_radius=radius,
        metadata={
            "methods": methods,
            "pool_size": len(pool),
            "ensemble_center": ensemble_center.tolist(),
            "calibration_margin": cfg.calibration_margin,
            "data_access_mode": "INSTRUMENTED_PREFIX_ONLY",
        },
    )
    candidates = pd.DataFrame(
        selected, columns=[f"n{index}" for index in range(1, 8)]
    )
    candidates.insert(0, "rank", np.arange(1, len(candidates) + 1))
    candidates.to_csv(output / "prediction_set.csv", index=False)
    atomic_write_json(output / "prediction_set.json", prediction_set.to_dict())
    atomic_write_json(output / "selection_trace.json", trace)
    ledger = ctx["recorder"].close()
    summary = build_summary(
        ctx=ctx,
        cfg=cfg,
        radius=radius,
        selected=selected,
        pool=pool,
        calibration_eval=calibration_eval,
        validation_eval=validation_eval,
        ledger=ledger,
    )
    atomic_write_json(output / "coverage_summary.json", summary)
    return summary


def build_summary(**values: Any) -> dict[str, Any]:
    ctx = values["ctx"]
    cfg = values["cfg"]
    validation_eval = values["validation_eval"]
    output = ctx["output"]
    return {
        "schema_version": "1.0.0",
        "run_id": ctx["current_run_id"],
        "status": (
            "TARGET_MET"
            if validation_eval.row_within_tolerance >= cfg.target_coverage
            else "TARGET_NOT_MET"
        ),
        "data_version": ctx["data_version"],
        "source_total_rows": ctx["source_total_rows"],
        "accessible_rows": len(ctx["data"]),
        "split": {
            "train_end": ctx["calibration_start"],
            "calibration": [ctx["calibration_start"], ctx["validation_start"]],
            "validation": [ctx["validation_start"], len(ctx["data"])],
            "protected_test": [
                ctx["protected_test_start"],
                ctx["source_total_rows"],
            ],
        },
        "target_coverage": cfg.target_coverage,
        "tolerance": cfg.tolerance,
        "candidate_count": len(values["selected"]),
        "pool_size": len(values["pool"]),
        "conformal_radius": values["radius"],
        "calibration": values["calibration_eval"].to_dict(),
        "validation": validation_eval.to_dict(),
        "protected_test_evaluated": False,
        "protected_test_materialized": False,
        "data_access_status": values["ledger"].status,
        "data_access_ledger": str(values["ledger"].ledger_path),
        "data_access_validation": str(values["ledger"].validation_path),
        "data_access_ledger_sha256": values["ledger"].ledger_sha256,
        "artifacts": {
            "prediction_set_csv": str(output / "prediction_set.csv"),
            "prediction_set_json": str(output / "prediction_set.json"),
            "selection_trace": str(output / "selection_trace.json"),
        },
        "note": (
            "Protected-test target rows were not parsed or materialized. The "
            "accessible prefix is not a memory sandbox."
        ),
    }
