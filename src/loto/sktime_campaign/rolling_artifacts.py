from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from loto.sktime_campaign.benchmark import (
    FORMAL_BASELINES,
    FORMAL_MODELS,
    canonical_sha256,
    compute_metrics,
)
from loto.sktime_campaign.rolling_origin import (
    RollingOriginRequest,
    aggregate_oof_results,
    build_oof_leaderboard,
    build_rolling_folds,
    expected_candidate_seed_keys,
    run_p3,
    verify_prediction_lock,
)


class P3VerificationError(RuntimeError):
    """Raised when P3 OOF or prediction-lock evidence fails verification."""


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    text = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    _atomic_write_text(path, text)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P3VerificationError(f"unable to read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_metadata(request: RollingOriginRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload["dataset"] = {
        **payload["dataset"],
        "values": "REDACTED_NOT_COPIED_TO_ARTIFACTS",
    }
    return payload


def _data_contract(request: RollingOriginRequest) -> dict[str, Any]:
    values = np.asarray(request.dataset.values, dtype=float)
    train_end = request.split.train_rows
    validation_end = train_end + request.split.validation_rows
    return {
        "schema_version": "1.0",
        "game_id": request.dataset.game_id,
        "position_names": request.dataset.position_names,
        "legal_min": request.dataset.legal_min,
        "legal_max": request.dataset.legal_max,
        "raw_rows": len(request.dataset.values),
        "raw_sha256": canonical_sha256(request.dataset.model_dump(mode="json")),
        "train_values_sha256": canonical_sha256(values[:train_end].tolist()),
        "validation_values_sha256": canonical_sha256(values[train_end:validation_end].tolist()),
        "holdout_values_sha256": canonical_sha256(values[validation_end:].tolist()),
        "visible_values_sha256": canonical_sha256(values[:validation_end].tolist()),
        "oof_scope": "TRAIN_ONLY",
        "holdout_prediction_fit_scope": "TRAIN_PLUS_VALIDATION_ONLY",
        "holdout_actual_access": "HASH_ONLY_NOT_SCORED",
    }


def _write_manifest_and_sha(output_dir: Path, *, status: str) -> None:
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": status,
        "scope": "sktime-p3-oof-holdout-prediction-lock",
        "files": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ],
    }
    _write_json(output_dir / "ARTIFACT_MANIFEST.json", manifest)
    hashed = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    _atomic_write_text(
        output_dir / "SHA256SUMS",
        "\n".join(f"{_sha256(path)}  {path.name}" for path in hashed) + "\n",
    )


def persist_p3(
    request: RollingOriginRequest,
    *,
    sealed_at_utc: str | None = None,
    model_predictor=None,
) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = run_p3(
        request,
        sealed_at_utc=sealed_at_utc,
        model_predictor=model_predictor,
    )
    response = {
        "schema_version": "1.0",
        "status": result["status"],
        "operation": request.operation,
        "stage": result["stage"],
        "run_id": request.run_id,
        "selected_oof_candidate_id": result["selected_oof_candidate_id"],
        "holdout_status": result["holdout_status"],
        "promotion_status": result["promotion_status"],
    }
    _write_json(output_dir / "REQUEST_METADATA.json", _request_metadata(request))
    _write_json(output_dir / "DATA_CONTRACT.json", _data_contract(request))
    _write_json(output_dir / "OOF_FOLDS.json", result["folds"])
    _write_json(output_dir / "OOF_RESULTS.json", result["oof_results"])
    _write_json(output_dir / "OOF_SEED_METRICS.json", result["oof_seed_metrics"])
    _write_json(
        output_dir / "OOF_CANDIDATE_AGGREGATES.json",
        result["oof_candidate_aggregates"],
    )
    _write_json(output_dir / "OOF_LEADERBOARD.json", result["oof_leaderboard"])
    _write_json(
        output_dir / "HOLDOUT_PREDICTION_LOCK.json",
        result["holdout_prediction_lock"],
    )
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir, status=result["status"])
    return response


def _verify_sha256sums(output_dir: Path) -> None:
    seen: set[str] = set()
    for line in (output_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        if name in seen:
            raise P3VerificationError(f"duplicate SHA path: {name}")
        seen.add(name)
        path = output_dir / name
        if not path.is_file() or _sha256(path) != expected:
            raise P3VerificationError(f"SHA-256 mismatch: {name}")
    expected_files = {
        path.name for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise P3VerificationError("SHA256SUMS coverage mismatch")


def _verify_manifest(output_dir: Path, *, expected_status: str) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != expected_status:
        raise P3VerificationError("manifest status mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        seen.add(name)
        if not path.is_file() or path.stat().st_size != int(record["size_bytes"]):
            raise P3VerificationError(f"manifest file/size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise P3VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P3VerificationError("manifest coverage mismatch")


def verify_p3(
    output_dir: Path,
    request: RollingOriginRequest,
    *,
    formal: bool = True,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    response = _load_json(output_dir / "response.json")
    status = str(response.get("status", ""))
    if status not in {"PASS", "PARTIAL", "FAILED", "UNAVAILABLE"}:
        raise P3VerificationError("invalid P3 response status")
    if response.get("holdout_status") != "PREDICTIONS_LOCKED_NOT_SCORED":
        raise P3VerificationError("Holdout status mismatch")
    if response.get("promotion_status") != "NOT_PROMOTED":
        raise P3VerificationError("P3 result was incorrectly promoted")
    if _load_json(output_dir / "REQUEST_METADATA.json") != _request_metadata(request):
        raise P3VerificationError("request metadata mismatch")
    if _load_json(output_dir / "DATA_CONTRACT.json") != _data_contract(request):
        raise P3VerificationError("data contract mismatch")
    if _load_json(output_dir / "OOF_FOLDS.json") != build_rolling_folds(request):
        raise P3VerificationError("OOF fold geometry mismatch")

    rows = _load_json(output_dir / "OOF_RESULTS.json")
    folds = build_rolling_folds(request)
    fold_lookup = {int(row["fold_id"]): row for row in folds}
    values = np.asarray(request.dataset.values, dtype=float)
    train_only = values[: request.split.train_rows]
    expected_keys = set(expected_candidate_seed_keys(request))
    observed_by_fold: dict[int, set[tuple[str, str, int]]] = {
        fold_id: set() for fold_id in fold_lookup
    }
    for row in rows:
        fold_id = int(row.get("fold_id", -1))
        if fold_id not in fold_lookup:
            raise P3VerificationError("OOF row references an unknown fold")
        fold = fold_lookup[fold_id]
        key = (
            str(row.get("candidate_kind")),
            str(row.get("candidate_id")),
            int(row.get("seed", -1)),
        )
        if key in observed_by_fold[fold_id]:
            raise P3VerificationError("duplicate candidate/seed within an OOF fold")
        observed_by_fold[fold_id].add(key)
        if row.get("fit_scope") != "OOF_TRAIN_PREFIX_ONLY":
            raise P3VerificationError("OOF row used wrong fit scope")
        if row.get("evaluation_scope") != "OOF_TRAIN_FUTURE_BLOCK_ONLY":
            raise P3VerificationError("OOF row used wrong evaluation scope")
        expected_train = train_only[fold["train_start"] : fold["train_end"]]
        expected_actual = train_only[fold["test_start"] : fold["test_end"]]
        if row.get("train_values_sha256") != canonical_sha256(expected_train.tolist()):
            raise P3VerificationError("OOF Train-prefix hash mismatch")
        if row.get("actual_values") != expected_actual.tolist():
            raise P3VerificationError("OOF actual values are not the fold future block")
        if row.get("test_draw_no") != fold["test_draw_no"]:
            raise P3VerificationError("OOF test draw identity mismatch")
        if row.get("actual_values_sha256") != canonical_sha256(row.get("actual_values")):
            raise P3VerificationError("OOF actual-value hash mismatch")
        if row.get("status") == "PASS":
            prediction = np.asarray(row["predictions"], dtype=float)
            if prediction.shape != expected_actual.shape or not np.isfinite(prediction).all():
                raise P3VerificationError("OOF prediction shape or finite check failed")
            expected = compute_metrics(
                expected_actual,
                prediction,
                position_names=request.dataset.position_names,
            )
            if row.get("metrics") != expected:
                raise P3VerificationError("OOF metrics mismatch")
    if any(observed != expected_keys for observed in observed_by_fold.values()):
        raise P3VerificationError("OOF candidate/seed inventory mismatch")

    seed_metrics, aggregates = aggregate_oof_results(rows)
    if _load_json(output_dir / "OOF_SEED_METRICS.json") != seed_metrics:
        raise P3VerificationError("OOF seed metrics mismatch")
    if _load_json(output_dir / "OOF_CANDIDATE_AGGREGATES.json") != aggregates:
        raise P3VerificationError("OOF candidate aggregates mismatch")
    leaderboard = build_oof_leaderboard(aggregates)
    if _load_json(output_dir / "OOF_LEADERBOARD.json") != leaderboard:
        raise P3VerificationError("OOF leaderboard mismatch")

    lock = _load_json(output_dir / "HOLDOUT_PREDICTION_LOCK.json")
    try:
        verify_prediction_lock(lock)
    except ValueError as exc:
        raise P3VerificationError(str(exc)) from exc
    visible_rows = request.split.train_rows + request.split.validation_rows
    if lock.get("visible_values_sha256") != canonical_sha256(values[:visible_rows].tolist()):
        raise P3VerificationError("prediction lock visible-data hash mismatch")
    if lock.get("holdout_draw_no") != request.dataset.draw_no[visible_rows:]:
        raise P3VerificationError("prediction lock Holdout draw identity mismatch")
    expected_selected = leaderboard[0]["candidate_id"] if leaderboard else None
    if lock.get("selected_oof_candidate_id") != expected_selected:
        raise P3VerificationError("prediction lock selected candidate mismatch")
    if response.get("selected_oof_candidate_id") != expected_selected:
        raise P3VerificationError("response selected candidate mismatch")
    lock_rows = lock.get("prediction_rows", [])
    observed_lock_keys: set[tuple[str, str, int]] = set()
    for row in lock_rows:
        key = (
            str(row.get("candidate_kind")),
            str(row.get("candidate_id")),
            int(row.get("seed", -1)),
        )
        if key in observed_lock_keys:
            raise P3VerificationError("duplicate candidate/seed in prediction lock")
        observed_lock_keys.add(key)
        if row.get("status") == "PASS":
            prediction = np.asarray(row.get("predictions"), dtype=float)
            expected_shape = (
                request.split.holdout_rows,
                len(request.dataset.position_names),
            )
            if prediction.shape != expected_shape or not np.isfinite(prediction).all():
                raise P3VerificationError("locked Holdout prediction shape or finite check failed")
    if observed_lock_keys != expected_keys:
        raise P3VerificationError("prediction-lock candidate/seed inventory mismatch")

    all_oof_pass = bool(rows) and all(row.get("status") == "PASS" for row in rows)
    all_lock_pass = bool(lock_rows) and all(row.get("status") == "PASS" for row in lock_rows)
    combined_rows = rows + lock_rows
    any_pass = any(row.get("status") == "PASS" for row in combined_rows)
    all_unavailable = bool(combined_rows) and all(
        row.get("status") == "UNAVAILABLE" for row in combined_rows
    )
    if all_oof_pass and all_lock_pass:
        recalculated = "PASS"
    elif any_pass:
        recalculated = "PARTIAL"
    elif all_unavailable:
        recalculated = "UNAVAILABLE"
    else:
        recalculated = "FAILED"
    if status != recalculated:
        raise P3VerificationError("aggregate P3 status mismatch")

    if formal:
        if request.baseline_ids != list(FORMAL_BASELINES):
            raise P3VerificationError("formal baseline inventory mismatch")
        if request.model_ids != list(FORMAL_MODELS):
            raise P3VerificationError("formal model inventory mismatch")
        if request.random_seeds != [1, 2, 3]:
            raise P3VerificationError("formal seeds must be [1, 2, 3]")
        if status != "PASS":
            raise P3VerificationError("formal P3 requires every OOF and lock row to PASS")

    _verify_manifest(output_dir, expected_status=status)
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p3-oof-holdout-prediction-lock",
        "p3_status": status,
        "fold_count": len(build_rolling_folds(request)),
        "oof_result_count": len(rows),
        "locked_prediction_count": len(lock_rows),
        "selected_oof_candidate_id": response.get("selected_oof_candidate_id"),
        "holdout_status": "PREDICTIONS_LOCKED_NOT_SCORED",
        "promotion_status": "NOT_PROMOTED",
    }
