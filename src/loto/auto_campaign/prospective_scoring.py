"""Actual ingestion and leakage-safe scoring for locked Prospective predictions."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .persistence import sha256_file, write_json, write_sha256s
from .prediction_lock import PREDICTION_LOCK_PATH
from .prospective_baselines import generate_prospective_baselines
from .prospective_scoring_metrics import (
    _add_combined_local_candidates,
    _baseline_comparison,
    _baseline_prediction_frame,
    _extract_locked_predictions,
    _score_candidates,
    _seed_summary,
    _write_table,
)
from .prospective_scoring_support import (
    ACTUALS_LOCK,
    ACTUALS_LOCK_SCHEMA_VERSION,
    ARTIFACT_MANIFEST,
    LOWER_BOUND,
    SCORING_REPORT,
    SCORING_SCHEMA_VERSION,
    UPPER_BOUND,
    ScoringOptions,
    _canonical_sha256,
    _code_sha256,
    _copy_source_evidence,
    _file_inventory,
    _normalize_input_table,
    _parse_utc,
    _require_regular_file,
    _source_fingerprint,
    _source_verification,
)
from .prospective_scoring_verification import verify_prospective_scoring


def score_locked_prospective_run(
    *,
    run_root: Path,
    actuals_path: Path,
    history_path: Path,
    output: Path,
    random_seed: int = 1,
    actual_source_label: str = "UNSPECIFIED",
    actual_published_at: str | None = None,
) -> dict[str, Any]:
    """Ingest actuals and score locked predictions without mutating the source run."""

    options = ScoringOptions(
        random_seed=random_seed,
        actual_source_label=actual_source_label,
        actual_published_at=actual_published_at,
    )
    run_root = run_root.resolve()
    actuals_path = actuals_path.resolve()
    history_path = history_path.resolve()
    output = output.resolve()
    _require_regular_file(actuals_path, "actuals input")
    _require_regular_file(history_path, "history input")
    if sha256_file(actuals_path) == sha256_file(history_path):
        raise ValueError("actuals and history inputs must be distinct files")
    if output.exists():
        raise FileExistsError(output)
    if output == run_root or run_root in output.parents:
        raise ValueError("scoring output must not be inside the locked source run")

    source_manifest, prediction_lock = _source_verification(run_root)
    source_before = _source_fingerprint(run_root)
    scoring_code_sha256 = _code_sha256(
        [
            Path(__file__),
            Path(generate_prospective_baselines.__code__.co_filename),
            Path(_extract_locked_predictions.__code__.co_filename),
            Path(_source_verification.__code__.co_filename),
            Path(verify_prospective_scoring.__code__.co_filename),
        ]
    )
    scoring_identity = {
        "prediction_lock_sha256": source_before[PREDICTION_LOCK_PATH],
        "history_sha256": sha256_file(history_path),
        "actuals_sha256": sha256_file(actuals_path),
        "scoring_code_sha256": scoring_code_sha256,
        "random_seed": options.random_seed,
        "actual_source_label": options.actual_source_label,
        "actual_published_at": options.actual_published_at,
    }
    scoring_id = f"prospective-score-{_canonical_sha256(scoring_identity)[:20]}"
    if sha256_file(history_path) != source_manifest.get("data_sha256"):
        raise ValueError(
            "history SHA-256 differs from the data used for prediction: "
            f"expected={source_manifest.get('data_sha256')}, "
            f"actual={sha256_file(history_path)}"
        )

    contract = json.loads((run_root / "data_contract.json").read_text(encoding="utf-8"))
    campaign_config = json.loads((run_root / "campaign_config.json").read_text(encoding="utf-8"))
    number_columns = [str(value) for value in contract.get("number_columns") or []]
    if len(number_columns) != 5:
        raise ValueError(f"Mini Loto scoring requires five positions: {number_columns}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prospective-scoring-", dir=output.parent) as temp:
        work = Path(temp) / "artifact"
        work.mkdir()
        source_evidence = _copy_source_evidence(run_root, work)
        input_dir = work / "inputs"
        input_dir.mkdir()
        history_copy = input_dir / f"history{history_path.suffix.casefold()}"
        actuals_copy = input_dir / f"actuals{actuals_path.suffix.casefold()}"
        shutil.copy2(history_path, history_copy)
        shutil.copy2(actuals_path, actuals_copy)
        if sha256_file(history_copy) != sha256_file(history_path):
            raise RuntimeError("history copy SHA mismatch")
        if sha256_file(actuals_copy) != sha256_file(actuals_path):
            raise RuntimeError("actuals copy SHA mismatch")

        model_predictions, prediction_copies, expected_ds = _extract_locked_predictions(
            run_root,
            prediction_lock,
            work,
            number_columns,
        )
        history = _normalize_input_table(
            history_copy,
            contract=contract,
            campaign_config=campaign_config,
            label="history",
        )
        actuals = _normalize_input_table(
            actuals_copy,
            contract=contract,
            campaign_config=campaign_config,
            label="actuals",
        )
        if len(history) != contract.get("rows"):
            raise ValueError(
                f"history row count differs from data contract: "
                f"expected={contract.get('rows')}, actual={len(history)}"
            )
        if int(history["draw_index"].iloc[-1]) != int(contract.get("last_draw_index")):
            raise ValueError("history last draw_index differs from data contract")
        history_last_index = int(history["draw_index"].iloc[-1])
        expected_sequence = list(
            range(
                history_last_index + 1,
                history_last_index + 1 + len(expected_ds),
            )
        )
        if expected_ds != expected_sequence:
            raise ValueError(
                f"prospective horizon is not immediately after history: "
                f"expected={expected_sequence}, prediction={expected_ds}"
            )
        actual_ds = actuals["draw_index"].astype(int).tolist()
        if actual_ds != expected_ds:
            raise ValueError(
                f"actual draw indices differ from locked prediction horizon: "
                f"expected={expected_ds}, actual={actual_ds}"
            )
        if set(actuals["draw_id"]) & set(history["draw_id"]):
            raise ValueError("actual draw IDs overlap prediction-time history")

        locked_at_failures: list[str] = []
        prediction_locked_at = _parse_utc(
            prediction_lock.get("locked_at"),
            locked_at_failures,
            "prediction locked_at",
        )
        published_at = None
        if options.actual_published_at is not None:
            published_at = _parse_utc(
                options.actual_published_at,
                locked_at_failures,
                "actual published_at",
            )
            if (
                prediction_locked_at is not None
                and published_at is not None
                and published_at < prediction_locked_at
            ):
                locked_at_failures.append("actual published_at precedes prediction lock")
        if locked_at_failures:
            raise ValueError("; ".join(locked_at_failures))

        model_predictions = _add_combined_local_candidates(
            model_predictions,
            number_columns,
        )
        history_matrix = history[number_columns].to_numpy(dtype=float)
        baselines, baseline_metadata = generate_prospective_baselines(
            history_matrix,
            horizon=len(expected_ds),
            lower=LOWER_BOUND,
            upper=UPPER_BOUND,
            random_seed=options.random_seed,
        )
        baseline_predictions = _baseline_prediction_frame(
            baselines,
            expected_ds=expected_ds,
            number_columns=number_columns,
            random_seed=options.random_seed,
        )
        all_predictions = pd.concat(
            [model_predictions, baseline_predictions],
            ignore_index=True,
        )
        metrics, position_metrics, scored_predictions = _score_candidates(
            all_predictions,
            actuals,
            number_columns=number_columns,
            expected_ds=expected_ds,
        )
        per_seed_metrics, seed_summary, ranking = _seed_summary(metrics)
        baseline_comparison, champion = _baseline_comparison(ranking)

        tables = {
            "history_normalized": _write_table(history, work, "HISTORY_NORMALIZED"),
            "actuals_normalized": _write_table(actuals, work, "ACTUALS_NORMALIZED"),
            "model_predictions": _write_table(
                model_predictions,
                work,
                "MODEL_PREDICTIONS",
            ),
            "baseline_predictions": _write_table(
                baseline_predictions,
                work,
                "BASELINE_PREDICTIONS",
            ),
            "scored_predictions": _write_table(
                scored_predictions,
                work,
                "SCORED_PREDICTIONS",
            ),
            "metrics": _write_table(metrics, work, "METRICS"),
            "position_metrics": _write_table(
                position_metrics,
                work,
                "POSITION_METRICS",
            ),
            "per_seed_metrics": _write_table(
                per_seed_metrics,
                work,
                "PER_SEED_METRICS",
            ),
            "seed_summary": _write_table(seed_summary, work, "SEED_SUMMARY"),
            "ranking": _write_table(ranking, work, "RANKING"),
            "baseline_comparison": _write_table(
                baseline_comparison,
                work,
                "BASELINE_COMPARISON",
            ),
        }
        write_json(work / "SOURCE_PREDICTION_MAP.json", prediction_copies)
        write_json(work / "BASELINE_METADATA.json", baseline_metadata)

        actuals_lock_payload: dict[str, Any] = {
            "schema_version": ACTUALS_LOCK_SCHEMA_VERSION,
            "status": "LOCKED",
            "scoring_id": scoring_id,
            "ingested_at": datetime.now(UTC).isoformat(),
            "actual_known": True,
            "actual_source_label": options.actual_source_label,
            "actual_published_at": (published_at.isoformat() if published_at is not None else None),
            "actual_publication_time_provided": published_at is not None,
            "actual_publication_time_verified": False,
            "prediction_locked_at": prediction_lock.get("locked_at"),
            "prediction_lock_sha256": source_evidence[PREDICTION_LOCK_PATH]["sha256"],
            "verification_seal_sha256": source_evidence["VERIFICATION_SEAL.json"]["sha256"],
            "history_input": {
                "path": history_copy.relative_to(work).as_posix(),
                "sha256": sha256_file(history_copy),
            },
            "actuals_input": {
                "path": actuals_copy.relative_to(work).as_posix(),
                "sha256": sha256_file(actuals_copy),
            },
            "actuals_normalized_sha256": sha256_file(work / "ACTUALS_NORMALIZED.parquet"),
            "draw_indices": expected_ds,
            "draw_ids": actuals["draw_id"].astype(str).tolist(),
            "number_columns": number_columns,
        }
        actuals_lock_payload["lock_sha256"] = _canonical_sha256(actuals_lock_payload)
        write_json(work / ACTUALS_LOCK, actuals_lock_payload)

        report = {
            "schema_version": SCORING_SCHEMA_VERSION,
            "status": "PASS",
            "scoring_id": scoring_id,
            "scoring_code_sha256": scoring_code_sha256,
            "created_at": datetime.now(UTC).isoformat(),
            "priority_metric": "hit_pm1",
            "source_run": str(run_root),
            "source_run_id": source_manifest.get("run_id"),
            "prediction_lock_sha256": source_evidence[PREDICTION_LOCK_PATH]["sha256"],
            "verification_seal_sha256": source_evidence["VERIFICATION_SEAL.json"]["sha256"],
            "history_sha256": sha256_file(history_copy),
            "actuals_sha256": sha256_file(actuals_copy),
            "draw_indices": expected_ds,
            "model_candidate_count": int(
                metrics[metrics["source_type"].eq("model")]["candidate_id"].nunique()
            ),
            "baseline_count": int(
                metrics[metrics["source_type"].eq("baseline")]["candidate_id"].nunique()
            ),
            "metric_rows": len(metrics),
            "position_metric_rows": len(position_metrics),
            "champion": champion,
            "baseline_names": sorted(baseline_predictions["baseline_name"].unique()),
            "actual_publication_time_provided": published_at is not None,
            "actual_publication_time_verified": False,
            "claim_boundary": (
                "The scoring artifact proves file hashes and ordering relative to the local "
                "prediction lock. It does not independently prove the official publication "
                "time of actual values unless actual_published_at was supplied and externally "
                "verified by the operator."
            ),
            "tables": tables,
        }
        write_json(work / SCORING_REPORT, report)

        manifest_payload: dict[str, Any] = {
            "schema_version": SCORING_SCHEMA_VERSION,
            "status": "PASS",
            "scoring_id": scoring_id,
            "scoring_code_sha256": scoring_code_sha256,
            "created_at": report["created_at"],
            "source_run": str(run_root),
            "source_run_id": source_manifest.get("run_id"),
            "source_evidence": source_evidence,
            "prediction_copy_count": len(prediction_copies),
            "actuals_lock_sha256": sha256_file(work / ACTUALS_LOCK),
            "scoring_report_sha256": sha256_file(work / SCORING_REPORT),
            "files": _file_inventory(work),
        }
        manifest_payload["manifest_sha256"] = _canonical_sha256(manifest_payload)
        write_json(work / ARTIFACT_MANIFEST, manifest_payload)
        write_sha256s(work)

        verification = verify_prospective_scoring(work)
        if verification.get("status") != "PASS":
            raise ValueError(
                "new prospective scoring artifact failed verification: "
                + "; ".join(verification.get("failures", []))
            )
        source_after = _source_fingerprint(run_root)
        if source_after != source_before:
            raise RuntimeError("source prospective run changed during scoring")
        _source_verification(run_root)
        os.replace(work, output)

    return {
        "status": "PASS",
        "schema_version": SCORING_SCHEMA_VERSION,
        "scoring_id": scoring_id,
        "scoring_code_sha256": scoring_code_sha256,
        "output": str(output),
        "source_run": str(run_root),
        "prediction_lock_sha256": source_before[PREDICTION_LOCK_PATH],
        "actuals_sha256": sha256_file(actuals_path),
        "history_sha256": sha256_file(history_path),
        "draw_indices": expected_ds,
        "champion": champion,
        "verification_status": "PASS",
    }
