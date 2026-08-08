from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from loto.autogluon_campaign.holdout_prospective import (
    LOCK_SCHEMA,
    GeometryContract,
    HoldoutProspectiveError,
    LockResult,
    SelectionEvidence,
    _canon,
    _digest,
    _empty,
    _history,
    _prediction_rows,
    _verify_hashes,
    _write,
    _write_evidence,
    build_baseline_predictions,
)


def create_prediction_lock(
    *,
    output_dir: Path,
    stage: str,
    run_id: str,
    geometry: GeometryContract,
    history_rows: Sequence[Mapping[str, Any]],
    future_draw_ids: Sequence[int],
    selection: SelectionEvidence,
    model_predictions: Sequence[Mapping[str, Any]],
    predecessor_score_dir: Path | None = None,
    now: datetime | None = None,
) -> LockResult:
    if stage not in {"holdout", "prospective"}:
        raise HoldoutProspectiveError("STAGE_INVALID", stage)
    history = _history(history_rows, geometry)
    future = tuple(future_draw_ids)
    start = history[-1]["draw_id"] + 1
    if future != tuple(range(start, start + geometry.horizon)):
        raise HoldoutProspectiveError("FUTURE_DRAW_IDS_INVALID", str(future))
    model_rows = _prediction_rows(model_predictions)
    observed = {(row.seed, row.draw_id) for row in model_rows}
    expected = {(seed, draw) for seed in selection.model_seeds for draw in future}
    if observed != expected or len(model_rows) != len(expected):
        raise HoldoutProspectiveError("MODEL_SEED_DRAW_COVERAGE_MISMATCH", str(observed))
    if any(row.candidate_id != selection.selected_candidate_id for row in model_rows):
        raise HoldoutProspectiveError("MODEL_CANDIDATE_MISMATCH", run_id)
    selection_payload = selection.model_dump(mode="json")
    if stage == "prospective":
        if predecessor_score_dir is None:
            raise HoldoutProspectiveError("HOLDOUT_SCORE_REQUIRED", run_id)
        from loto.autogluon_campaign.holdout_prospective_score import (
            verify_scoring_output,
        )

        report = verify_scoring_output(predecessor_score_dir)["report"]
        if report["stage"] != "holdout" or report["status"] != "PASS":
            raise HoldoutProspectiveError("HOLDOUT_SCORE_REQUIRED", run_id)
        if report["selected_candidate_id"] != selection.selected_candidate_id:
            raise HoldoutProspectiveError("SHADOW_CANDIDATE_CHANGED", run_id)
        selection_payload["holdout_score_sha256"] = report["report_sha256"]
        selection_payload["holdout_reference_metrics"] = report["selected_candidate_metrics"]
    baselines = build_baseline_predictions(history, future, geometry)
    root = _empty(output_dir)
    payloads = {
        "GEOMETRY.json": geometry.model_dump(mode="json"),
        "HISTORY.json": {"rows": history},
        "SELECTION_EVIDENCE.json": selection_payload,
        "MODEL_PREDICTIONS.json": {"rows": [row.model_dump(mode="json") for row in model_rows]},
        "BASELINE_PREDICTIONS.json": {"rows": [row.model_dump(mode="json") for row in baselines]},
    }
    for name, payload in payloads.items():
        _write(root / name, payload)
    core = {
        "schema_version": LOCK_SCHEMA,
        "stage": stage,
        "run_id": run_id,
        "locked_at": (now or datetime.now(timezone.utc)).isoformat(),
        "timestamp_authority": "LOCAL_SYSTEM_UTC",
        "actual_known": False,
        "evaluation_status": "NOT_SCORED",
        "promotion_status": "SHADOW_NOT_PROMOTED",
        "selected_candidate_id": selection.selected_candidate_id,
        "model_seeds": list(selection.model_seeds),
        "future_draw_ids": list(future),
        "automatic_promotion": False,
        "automatic_retraining": False,
    }
    lock = {**core, "lock_sha256": _digest(_canon(core))}
    _write(root / "PREDICTION_LOCK.json", lock)
    _write_evidence(root, [*payloads, "PREDICTION_LOCK.json"])
    verify_prediction_lock(root)
    return LockResult(
        str(root),
        str(root / "PREDICTION_LOCK.json"),
        lock["lock_sha256"],
        stage,
        selection.selected_candidate_id,
        len(model_rows),
        len(baselines),
    )


def verify_prediction_lock(root: Path) -> dict[str, Any]:
    root = root.resolve()
    required = {
        "GEOMETRY.json",
        "HISTORY.json",
        "SELECTION_EVIDENCE.json",
        "MODEL_PREDICTIONS.json",
        "BASELINE_PREDICTIONS.json",
        "PREDICTION_LOCK.json",
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    }
    observed = _verify_hashes(root, "LOCK")
    if observed != required:
        raise HoldoutProspectiveError("LOCK_FILE_SET_MISMATCH", str(observed))
    lock = json.loads((root / "PREDICTION_LOCK.json").read_text())
    claimed = lock.pop("lock_sha256")
    if claimed != _digest(_canon(lock)):
        raise HoldoutProspectiveError("LOCK_CANONICAL_HASH_MISMATCH", claimed)
    lock["lock_sha256"] = claimed
    return lock
