from __future__ import annotations

import hashlib
import json
import traceback
import uuid
from pathlib import Path
from typing import Any

from loto.data_access_ledger import AccessDecision
from loto.orchestration.formal_backtest_entrypoint_support import (
    atomic_write_json,
    baselines,
    build_parser,
    dataset_evidence,
    load_legacy_module,
    load_manifest,
    require_empty_output,
    resolve_data_path,
)
from loto.orchestration.formal_backtest_execution import run_instrumented_fold
from loto.orchestration.formal_backtest_ledger import (
    FormalBacktestLedgerBlocked,
    FormalBacktestLedgerRecorder,
)


def main() -> None:
    module = load_legacy_module()
    args = build_parser(module).parse_args()
    if args.resume:
        raise SystemExit("instrumented formal backtest requires --no-resume")

    output_dir = Path(args.output).expanduser().absolute()
    require_empty_output(output_dir)
    data_path = resolve_data_path(args.data)
    manifest = load_manifest(data_path)
    full_df, canonical_manifest = module.canonicalize_loto7(
        module.pd.read_csv(data_path), source=str(data_path)
    )
    if canonical_manifest.sha256 != manifest["canonical_data_sha256"]:
        raise SystemExit(
            "canonical data hash differs from data_manifest.json: "
            f"{canonical_manifest.sha256} != {manifest['canonical_data_sha256']}"
        )
    if len(full_df) != int(manifest["row_count"]):
        raise SystemExit(
            "canonical row count differs from manifest: "
            f"{len(full_df)} != {manifest['row_count']}"
        )

    test_draws = args.test_draws
    if test_draws is None:
        test_draws = (
            10
            if args.stage == "smoke"
            else 30
            if args.stage == "screening"
            else 100
        )
    if len(full_df) - test_draws < args.min_train_draws:
        raise SystemExit(
            "Insufficient history for requested chronological lane: "
            f"N={len(full_df)}, test_draws={test_draws}, "
            f"min_train={args.min_train_draws}"
        )

    run_id = args.data_access_run_id or f"formal-ledger-{uuid.uuid4().hex[:12]}"
    recorder = FormalBacktestLedgerRecorder(
        run_id=run_id,
        output_dir=output_dir,
        evidence=dataset_evidence(
            master=full_df,
            manifest=manifest,
            data_path=data_path,
        ),
        seed=args.seed,
        resume=args.resume,
    )
    specs = module.list_model_specs(available_only=args.available_only)
    if args.models != "all":
        requested = {item.strip() for item in args.models.split(",") if item.strip()}
        specs = [item for item in specs if item.model_id in requested]
    if not specs:
        recorder.record_failure(
            model_id="__catalog__", fold_id="__none__", reason="NO_MODELS"
        )
        recorder.close()
        raise SystemExit("No models selected")

    data_hash = str(manifest["canonical_data_sha256"])
    code_fingerprint = module.compute_code_fingerprint()
    geometry = module.geometry_for("loto7")
    baseline_ids = baselines()
    n_rows = len(full_df)

    for spec in specs:
        model_id = spec.model_id
        model_config_hash = hashlib.sha256(
            json.dumps(spec.to_dict(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        model_run_dir = output_dir / model_id
        for offset in range(test_draws):
            test_idx = n_rows - test_draws + offset
            test_row = full_df.iloc[[test_idx]]
            train_df = full_df.iloc[:test_idx]
            train_start = int(train_df["draw_no"].min())
            train_end = int(train_df["draw_no"].max())
            test_draw_no = int(test_row.iloc[0]["draw_no"])
            fold_id = f"fold-{test_draw_no}"
            recorder.register_fold(model_id=model_id, fold_id=fold_id)
            signature = module.generate_fold_signature(
                model_id=model_id,
                data_hash=data_hash,
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                test_draw=test_draw_no,
                model_config_hash=model_config_hash,
                code_fingerprint=code_fingerprint,
                seed=args.seed,
                stage=args.stage,
                device=args.device,
                precision=args.precision,
            )
            fold_dir = model_run_dir / fold_id
            fold_dir.mkdir(parents=True, exist_ok=True)
            leakage: dict[str, Any] = {
                "status": "LEAKAGE_NOT_VERIFIED",
                "reason": "fold failed before leakage checks completed",
            }
            device_evidence: dict[str, Any] = {
                "requested_device": args.device,
                "resolved_device": "unknown",
                "gpu_used": None,
            }
            status = "PASS"
            error_message = ""
            try:
                (
                    candidate_probs,
                    pos_pred,
                    resolved_params,
                    duration,
                    peak_vram,
                    leakage,
                    device_evidence,
                ) = run_instrumented_fold(
                    module=module,
                    recorder=recorder,
                    model_id=model_id,
                    fold_id=fold_id,
                    spec=spec,
                    train_df=train_df,
                    test_row=test_row,
                    full_df=full_df,
                    test_idx=test_idx,
                    seed=args.seed,
                    device=args.device,
                    precision=args.precision,
                    stage=args.stage,
                )
                actual_pos = test_row[
                    [f"n{index}" for index in range(1, 8)]
                ].to_numpy(int).reshape(1, -1)
                actual_candidates = module.np.zeros((1, 37))
                for value in actual_pos[0]:
                    actual_candidates[0, value - 1] = 1.0
                metrics = module.evaluate_all(
                    actual=actual_pos,
                    predicted=pos_pred.reshape(1, -1),
                    geometry=geometry,
                    targets=actual_candidates,
                    probabilities=candidate_probs.reshape(1, -1),
                )
                atomic_write_json(
                    fold_dir / "prediction.json",
                    {
                        "position_predictions": pos_pred.tolist(),
                        "candidate_probabilities": candidate_probs.tolist(),
                    },
                )
                atomic_write_json(fold_dir / "metrics.json", metrics)
                atomic_write_json(
                    fold_dir / "resource_evidence.json",
                    {
                        "duration_seconds": duration,
                        "peak_vram_mib": peak_vram,
                        **device_evidence,
                    },
                )
                atomic_write_json(
                    fold_dir / "lifecycle.json",
                    {
                        "fit_status": "PASS",
                        "predict_status": "PASS",
                        "resolved_params": resolved_params,
                    },
                )
                baseline_metrics: dict[str, Any] = {}
                for baseline in baseline_ids:
                    baseline_probs, baseline_pos = module.get_baseline_predictions(
                        baseline, train_df, test_row, args.seed
                    )
                    baseline_metrics[baseline] = module.evaluate_all(
                        actual=actual_pos,
                        predicted=baseline_pos.reshape(1, -1),
                        geometry=geometry,
                        targets=actual_candidates,
                        probabilities=baseline_probs.reshape(1, -1),
                    )
                atomic_write_json(fold_dir / "baselines.json", baseline_metrics)
                atomic_write_json(fold_dir / "leakage_evidence.json", leakage)
                if leakage.get("status") != "PASS":
                    recorder.record_failure(
                        model_id=model_id,
                        fold_id=fold_id,
                        reason=(
                            "LEAKAGE_STATUS_"
                            f"{leakage.get('status', 'LEAKAGE_NOT_VERIFIED')}"
                        ),
                    )
                recorder.record_score(model_id=model_id, fold_id=fold_id)
            except SystemExit as exc:
                status = "FAIL"
                error_message = f"SystemExit: {exc}"
                recorder.record_failure(
                    model_id=model_id,
                    fold_id=fold_id,
                    reason=error_message,
                )
                atomic_write_json(
                    fold_dir / "error.json",
                    {
                        "error": error_message,
                        "traceback": traceback.format_exc(),
                    },
                )
                raise
            except Exception as exc:
                status = "FAIL"
                error_message = f"{type(exc).__name__}: {exc}"
                recorder.record_failure(
                    model_id=model_id,
                    fold_id=fold_id,
                    reason=error_message,
                )
                atomic_write_json(
                    fold_dir / "error.json",
                    {
                        "error": error_message,
                        "traceback": traceback.format_exc(),
                    },
                )
                if args.fail_fast:
                    raise
            finally:
                atomic_write_json(
                    fold_dir / "fold_manifest.json",
                    {
                        "model_id": model_id,
                        "fold_id": fold_id,
                        "status": status,
                        "signature": signature,
                        "train_start": train_start,
                        "train_end": train_end,
                        "test_draw": test_draw_no,
                        "error": error_message,
                        "leakage_status": leakage.get(
                            "status", "LEAKAGE_NOT_VERIFIED"
                        ),
                        "data_access_run_id": run_id,
                    },
                )

    report = recorder.close()
    if report.status is not AccessDecision.PASS:
        raise FormalBacktestLedgerBlocked(
            f"formal backtest data access status={report.status.value}"
        )
    print(
        json.dumps(
            {
                "status": report.status.value,
                "run_id": report.run_id,
                "ledger_sha256": report.ledger_sha256,
                "verified_events": report.verified_events,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


__all__ = ["main"]
