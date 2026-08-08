from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from loto.sktime_campaign.benchmark import (
    FORMAL_BASELINES,
    FORMAL_MODELS,
    BaselineId,
    canonical_sha256,
)
from loto.sktime_campaign.prospective import (
    ProspectiveMonitoringRequest,
    ProspectiveRequest,
    expected_candidate_seed_keys,
    monitor_prospective,
    run_prospective_lock,
    verify_prospective_lock,
)


class P5VerificationError(RuntimeError):
    """Raised when P5 Prospective evidence fails exact verification."""


class P4LineageContext(BaseModel):
    """Verified P4 identities required before creating Prospective predictions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    p4_status: Literal["PASS"] = "PASS"
    p4_promotion_status: Literal["NOT_PROMOTED"] = "NOT_PROMOTED"
    p4_selected_oof_candidate_id: str = Field(min_length=1)
    p4_response_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p4_sha256sums_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p4_candidate_aggregates_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


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
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P5VerificationError(f"unable to read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest_and_sha(
    output_dir: Path,
    *,
    status: str,
    scope: str,
) -> None:
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": status,
        "scope": scope,
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


def _verify_sha256sums(output_dir: Path) -> None:
    sums_path = output_dir / "SHA256SUMS"
    if not sums_path.is_file():
        raise P5VerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        try:
            expected, relative_name = line.split("  ", maxsplit=1)
        except ValueError as exc:
            raise P5VerificationError("invalid SHA256SUMS line") from exc
        if relative_name in seen:
            raise P5VerificationError(f"duplicate SHA path: {relative_name}")
        seen.add(relative_name)
        path = output_dir / relative_name
        if not path.is_file() or _sha256(path) != expected:
            raise P5VerificationError(f"SHA-256 mismatch: {relative_name}")
    expected_files = {
        path.name for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise P5VerificationError("SHA256SUMS coverage mismatch")


def _verify_manifest(
    output_dir: Path,
    *,
    expected_status: str,
    expected_scope: str,
) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != expected_status:
        raise P5VerificationError("manifest status mismatch")
    if manifest.get("scope") != expected_scope:
        raise P5VerificationError("manifest scope mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        if name in seen:
            raise P5VerificationError(f"duplicate manifest path: {name}")
        seen.add(name)
        if not path.is_file():
            raise P5VerificationError(f"manifest file missing: {name}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise P5VerificationError(f"manifest size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise P5VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P5VerificationError("manifest coverage mismatch")


def _formal_keys() -> list[tuple[str, str, int]]:
    keys: list[tuple[str, str, int]] = []
    for baseline in FORMAL_BASELINES:
        seeds = [1, 2, 3] if baseline is BaselineId.RANDOM_UNIFORM else [1]
        keys.extend(("baseline", baseline.value, seed) for seed in seeds)
    keys.extend(("sktime", model.value, 1) for model in FORMAL_MODELS)
    return keys


def _lock_row_keys(lock: dict[str, Any]) -> list[tuple[str, str, int]]:
    keys = [
        (
            str(row.get("candidate_kind")),
            str(row.get("candidate_id")),
            int(row.get("seed")),
        )
        for row in lock.get("prediction_rows", [])
    ]
    if len(keys) != len(set(keys)):
        raise P5VerificationError("duplicate candidate/seed in Prospective lock")
    return keys


def _request_metadata(request: ProspectiveRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload["history"] = {
        **payload["history"],
        "values": "REDACTED_SEE_HISTORY_CONTRACT_SHA256",
    }
    return payload


def _history_contract(request: ProspectiveRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "game_id": request.history.game_id,
        "history_rows": len(request.history.values),
        "history_cutoff_draw_no": request.history.draw_no[-1],
        "history_draw_no_sha256": canonical_sha256(request.history.draw_no),
        "history_values_sha256": canonical_sha256(request.history.values),
        "position_names": request.history.position_names,
        "legal_min": request.history.legal_min,
        "legal_max": request.history.legal_max,
        "prospective_draw_no": request.prospective_draw_no,
        "prospective_draw_no_sha256": canonical_sha256(request.prospective_draw_no),
        "fit_scope": "OBSERVED_HISTORY_ONLY",
        "future_actual_access": "IDENTITIES_ONLY_NOT_SCORED",
    }


def _p4_lineage(
    request: ProspectiveRequest,
    context: P4LineageContext,
) -> dict[str, Any]:
    if context.p4_selected_oof_candidate_id != request.p4_selected_oof_candidate_id:
        raise P5VerificationError("P4 selected candidate differs from P5 request")
    return {
        "schema_version": "1.0",
        **context.model_dump(mode="json"),
        "bound_p4_artifact_sha256": request.p4_artifact_sha256,
        "selection_source": "P3_OOF_VIA_VERIFIED_P4_LINEAGE",
        "holdout_reselection": False,
        "promotion_status": "NOT_PROMOTED",
    }


def persist_prospective_lock(
    request: ProspectiveRequest,
    context: P4LineageContext,
    *,
    sealed_at_utc: str | None = None,
    model_predictor=None,
) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    lineage = _p4_lineage(request, context)
    result = run_prospective_lock(
        request,
        sealed_at_utc=sealed_at_utc,
        model_predictor=model_predictor,
    )
    lock = result["prediction_lock"]
    response = {
        "schema_version": "1.0",
        "status": result["status"],
        "operation": request.operation,
        "stage": result["stage"],
        "run_id": request.run_id,
        "shadow_candidate_id": result["shadow_candidate_id"],
        "prospective_status": result["prospective_status"],
        "promotion_status": result["promotion_status"],
        "max_workers": request.max_workers,
        "actuals_known": False,
        "model_execution": True,
        "retraining": False,
        "holdout_reselection": False,
    }
    _write_json(output_dir / "REQUEST_METADATA.json", _request_metadata(request))
    _write_json(output_dir / "HISTORY_CONTRACT.json", _history_contract(request))
    _write_json(output_dir / "P4_LINEAGE.json", lineage)
    _write_json(output_dir / "PROSPECTIVE_PREDICTION_LOCK.json", lock)
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(
        output_dir,
        status=result["status"],
        scope="sktime-p5-prospective-shadow-lock",
    )
    return response


def verify_prospective_bundle(
    output_dir: Path,
    request: ProspectiveRequest,
    context: P4LineageContext,
    *,
    formal: bool = True,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if _load_json(output_dir / "REQUEST_METADATA.json") != _request_metadata(request):
        raise P5VerificationError("request metadata mismatch")
    if _load_json(output_dir / "HISTORY_CONTRACT.json") != _history_contract(request):
        raise P5VerificationError("history contract mismatch")
    if _load_json(output_dir / "P4_LINEAGE.json") != _p4_lineage(request, context):
        raise P5VerificationError("P4 lineage mismatch")

    lock = _load_json(output_dir / "PROSPECTIVE_PREDICTION_LOCK.json")
    verify_prospective_lock(lock)
    if lock.get("run_id") != request.run_id:
        raise P5VerificationError("Prospective lock run ID mismatch")
    if lock.get("git_commit") != request.git_commit:
        raise P5VerificationError("Prospective lock Git commit mismatch")
    if lock.get("code_sha256") != request.code_sha256:
        raise P5VerificationError("Prospective lock code hash mismatch")
    if lock.get("config_sha256") != request.config_sha256:
        raise P5VerificationError("Prospective lock config hash mismatch")
    if lock.get("p4_artifact_sha256") != request.p4_artifact_sha256:
        raise P5VerificationError("Prospective lock P4 lineage mismatch")
    if lock.get("shadow_candidate_id") != request.p4_selected_oof_candidate_id:
        raise P5VerificationError("Prospective lock changed shadow candidate")
    if lock.get("max_workers") != request.max_workers:
        raise P5VerificationError("Prospective lock worker count mismatch")
    if lock.get("history_sha256") != canonical_sha256(
        {
            "draw_no": request.history.draw_no,
            "values": request.history.values,
        }
    ):
        raise P5VerificationError("Prospective history hash mismatch")
    if lock.get("prospective_draw_no") != request.prospective_draw_no:
        raise P5VerificationError("Prospective draw identities mismatch")
    if _lock_row_keys(lock) != expected_candidate_seed_keys(request):
        raise P5VerificationError("candidate/seed inventory differs from request")

    rows = lock.get("prediction_rows", [])
    for row in rows:
        if row.get("device") != "cpu" or row.get("cpu_fallback") is not False:
            raise P5VerificationError("Prospective row device boundary mismatch")
        if row.get("status") == "PASS":
            expected_shape = [
                len(request.prospective_draw_no),
                len(request.history.position_names),
            ]
            if row.get("prediction_shape") != expected_shape:
                raise P5VerificationError("Prospective prediction shape mismatch")
            if row.get("prediction_finite") is not True:
                raise P5VerificationError("Prospective finite-value flag mismatch")
    all_pass = bool(rows) and all(row.get("status") == "PASS" for row in rows)
    any_pass = any(row.get("status") == "PASS" for row in rows)
    all_unavailable = bool(rows) and all(row.get("status") == "UNAVAILABLE" for row in rows)
    expected_status = (
        "PASS"
        if all_pass
        else ("PARTIAL" if any_pass else ("UNAVAILABLE" if all_unavailable else "FAILED"))
    )

    response = _load_json(output_dir / "response.json")
    if response.get("status") != expected_status:
        raise P5VerificationError("Prospective response status mismatch")
    if response.get("shadow_candidate_id") != request.p4_selected_oof_candidate_id:
        raise P5VerificationError("Prospective response changed shadow candidate")
    if response.get("promotion_status") != "SHADOW_NOT_PROMOTED":
        raise P5VerificationError("Prospective response incorrectly claims promotion")
    if response.get("actuals_known") is not False:
        raise P5VerificationError("Prospective response incorrectly claims actuals")
    if formal:
        if request.baseline_ids != list(FORMAL_BASELINES):
            raise P5VerificationError("formal baseline inventory mismatch")
        if request.model_ids != list(FORMAL_MODELS):
            raise P5VerificationError("formal model inventory mismatch")
        if request.random_seeds != [1, 2, 3]:
            raise P5VerificationError("formal random seeds must be [1, 2, 3]")
        if request.max_workers != 8:
            raise P5VerificationError("formal Prospective execution requires 8 workers")
        if _lock_row_keys(lock) != _formal_keys():
            raise P5VerificationError("formal candidate/seed inventory mismatch")
        if lock.get("thread_limits") != {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }:
            raise P5VerificationError("formal numerical thread limits mismatch")
        if expected_status != "PASS":
            raise P5VerificationError(
                "formal Prospective lock requires every candidate/seed to PASS"
            )

    _verify_manifest(
        output_dir,
        expected_status=expected_status,
        expected_scope="sktime-p5-prospective-shadow-lock",
    )
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p5-prospective-shadow-lock",
        "prediction_status": expected_status,
        "candidate_seed_count": len(rows),
        "shadow_candidate_id": request.p4_selected_oof_candidate_id,
        "max_workers": request.max_workers,
        "actuals_known": False,
        "promotion_status": "SHADOW_NOT_PROMOTED",
    }


def _monitor_lock_lineage(request: ProspectiveMonitoringRequest) -> dict[str, Any]:
    lock = request.prediction_lock
    return {
        "schema_version": "1.0",
        "run_id": lock["run_id"],
        "sealed_at_utc": lock["sealed_at_utc"],
        "seal_sha256": lock["seal_sha256"],
        "shadow_candidate_id": lock["shadow_candidate_id"],
        "prospective_draw_no": lock["prospective_draw_no"],
        "prospective_draw_no_sha256": lock["prospective_draw_no_sha256"],
        "history_sha256": lock["history_sha256"],
        "selection_source": lock["selection_source"],
        "prediction_source": "P5_LOCK_ONLY_NO_REFIT_NO_REPREDICT",
    }


def persist_prospective_monitor(
    request: ProspectiveMonitoringRequest,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")
    result = monitor_prospective(request)
    drift_report = {
        "schema_version": "1.0",
        "shadow_candidate_id": result["shadow_candidate_id"],
        "drift_status": result["drift_status"],
        "alerts": result["alerts"],
        "recommendation": result["recommendation"],
        "policy": request.policy.model_dump(mode="json"),
        "holdout_reference_metrics": request.holdout_reference_metrics,
        "automatic_retraining": False,
        "automatic_promotion": False,
        "promotion_status": "NOT_PROMOTED",
    }
    response = {
        "schema_version": "1.0",
        "status": result["status"],
        "operation": request.operation,
        "stage": result["stage"],
        "run_id": request.run_id,
        "shadow_candidate_id": result["shadow_candidate_id"],
        "drift_status": result["drift_status"],
        "recommendation": result["recommendation"],
        "automatic_retraining": False,
        "automatic_promotion": False,
        "promotion_status": "NOT_PROMOTED",
    }
    _write_json(
        output_dir / "ACTUALS_SNAPSHOT.json",
        request.actuals.model_dump(mode="json"),
    )
    _write_json(
        output_dir / "P5_LOCK_LINEAGE.json",
        _monitor_lock_lineage(request),
    )
    _write_json(
        output_dir / "PROSPECTIVE_RESULTS.json",
        result["score_rows"],
    )
    _write_json(
        output_dir / "CANDIDATE_AGGREGATES.json",
        result["candidate_aggregates"],
    )
    _write_json(
        output_dir / "PROSPECTIVE_LEADERBOARD.json",
        result["leaderboard"],
    )
    _write_json(output_dir / "DRIFT_REPORT.json", drift_report)
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(
        output_dir,
        status=result["status"],
        scope="sktime-p5-prospective-monitoring",
    )
    return response


def verify_prospective_monitor(
    output_dir: Path,
    request: ProspectiveMonitoringRequest,
    *,
    formal: bool = True,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    verify_prospective_lock(request.prediction_lock)
    expected = monitor_prospective(request)

    if _load_json(output_dir / "ACTUALS_SNAPSHOT.json") != request.actuals.model_dump(mode="json"):
        raise P5VerificationError("Prospective actual snapshot mismatch")
    if _load_json(output_dir / "P5_LOCK_LINEAGE.json") != _monitor_lock_lineage(request):
        raise P5VerificationError("Prospective lock lineage mismatch")
    if _load_json(output_dir / "PROSPECTIVE_RESULTS.json") != expected["score_rows"]:
        raise P5VerificationError("Prospective result rows mismatch")
    if _load_json(output_dir / "CANDIDATE_AGGREGATES.json") != expected["candidate_aggregates"]:
        raise P5VerificationError("Prospective candidate aggregates mismatch")
    if _load_json(output_dir / "PROSPECTIVE_LEADERBOARD.json") != expected["leaderboard"]:
        raise P5VerificationError("Prospective leaderboard mismatch")

    expected_drift = {
        "schema_version": "1.0",
        "shadow_candidate_id": expected["shadow_candidate_id"],
        "drift_status": expected["drift_status"],
        "alerts": expected["alerts"],
        "recommendation": expected["recommendation"],
        "policy": request.policy.model_dump(mode="json"),
        "holdout_reference_metrics": request.holdout_reference_metrics,
        "automatic_retraining": False,
        "automatic_promotion": False,
        "promotion_status": "NOT_PROMOTED",
    }
    if _load_json(output_dir / "DRIFT_REPORT.json") != expected_drift:
        raise P5VerificationError("Prospective drift report mismatch")

    response = _load_json(output_dir / "response.json")
    if response.get("status") != expected["status"]:
        raise P5VerificationError("Prospective monitoring status mismatch")
    if response.get("shadow_candidate_id") != request.prediction_lock.get("shadow_candidate_id"):
        raise P5VerificationError("Prospective monitoring changed shadow candidate")
    if response.get("automatic_retraining") is not False:
        raise P5VerificationError("Prospective monitor enabled automatic retraining")
    if response.get("automatic_promotion") is not False:
        raise P5VerificationError("Prospective monitor enabled automatic promotion")
    if response.get("promotion_status") != "NOT_PROMOTED":
        raise P5VerificationError("Prospective monitor incorrectly claims promotion")

    rows = expected["score_rows"]
    all_pass = bool(rows) and all(row.get("status") == "PASS" for row in rows)
    if formal and not all_pass:
        raise P5VerificationError(
            "formal Prospective monitoring requires every locked row to score"
        )

    _verify_manifest(
        output_dir,
        expected_status=expected["status"],
        expected_scope="sktime-p5-prospective-monitoring",
    )
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p5-prospective-monitoring",
        "monitoring_status": expected["status"],
        "drift_status": expected["drift_status"],
        "recommendation": expected["recommendation"],
        "shadow_candidate_id": expected["shadow_candidate_id"],
        "automatic_retraining": False,
        "automatic_promotion": False,
        "promotion_status": "NOT_PROMOTED",
    }
