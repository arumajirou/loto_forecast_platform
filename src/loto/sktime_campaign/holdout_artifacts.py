from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loto.sktime_campaign.holdout_scoring import (
    HoldoutScoringRequest,
    score_holdout,
)


class P4VerificationError(RuntimeError):
    """Raised when sealed Holdout scoring evidence fails verification."""


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
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P4VerificationError(f"unable to read JSON {path}: {exc}") from exc


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_metadata(request: HoldoutScoringRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload["actuals"] = {
        **payload["actuals"],
        "values": "STORED_SEPARATELY_IN_HOLDOUT_ACTUALS_JSON",
    }
    return payload


def _write_manifest_and_sha(output_dir: Path, *, status: str) -> None:
    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in excluded
    )
    manifest = {
        "schema_version": "1.0",
        "status": status,
        "scope": "sktime-p4-sealed-holdout-scoring",
        "files": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in files
        ],
    }
    _write_json(output_dir / "ARTIFACT_MANIFEST.json", manifest)
    hashed = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    )
    _atomic_write_text(
        output_dir / "SHA256SUMS",
        "\n".join(
            f"{file_sha256(path)}  {path.name}"
            for path in hashed
        )
        + "\n",
    )


def persist_p4(
    request: HoldoutScoringRequest,
    lock: dict[str, Any],
    *,
    formal: bool = True,
) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")

    result = score_holdout(request, lock, formal=formal)
    response = {
        "schema_version": "1.0",
        "status": result["status"],
        "operation": request.operation,
        "stage": result["stage"],
        "run_id": request.run_id,
        "scored_at_utc": request.scored_at_utc,
        "candidate_result_count": len(result["holdout_results"]),
        "candidate_aggregate_count": len(result["candidate_aggregates"]),
        "selected_oof_candidate_id": result["selected_oof_candidate_id"],
        "selected_holdout_rank": result["baseline_comparison"].get(
            "selected_holdout_rank"
        ),
        "scoring_scope": result["scoring_scope"],
        "model_execution": False,
        "retraining": False,
        "reprediction": False,
        "promotion_status": result["promotion_status"],
    }
    _write_json(output_dir / "REQUEST_METADATA.json", _request_metadata(request))
    _write_json(
        output_dir / "P3_LINEAGE.json",
        result["prediction_lock_lineage"],
    )
    _write_json(
        output_dir / "HOLDOUT_ACTUALS.json",
        request.actuals.model_dump(mode="json"),
    )
    _write_json(
        output_dir / "HOLDOUT_RESULTS.json",
        result["holdout_results"],
    )
    _write_json(
        output_dir / "HOLDOUT_CANDIDATE_AGGREGATES.json",
        result["candidate_aggregates"],
    )
    _write_json(
        output_dir / "HOLDOUT_LEADERBOARD.json",
        result["leaderboard"],
    )
    _write_json(
        output_dir / "BASELINE_COMPARISON.json",
        result["baseline_comparison"],
    )
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir, status=result["status"])
    return response


def _verify_sha256sums(output_dir: Path) -> None:
    path = output_dir / "SHA256SUMS"
    if not path.is_file():
        raise P4VerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            expected, name = line.split("  ", maxsplit=1)
        except ValueError as exc:
            raise P4VerificationError("malformed SHA256SUMS line") from exc
        if name in seen:
            raise P4VerificationError(f"duplicate SHA path: {name}")
        seen.add(name)
        target = output_dir / name
        if not target.is_file() or file_sha256(target) != expected:
            raise P4VerificationError(f"SHA-256 mismatch: {name}")
    expected_files = {
        item.name
        for item in output_dir.iterdir()
        if item.is_file() and item.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise P4VerificationError("SHA256SUMS coverage mismatch")


def _verify_manifest(output_dir: Path, *, expected_status: str) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("scope") != "sktime-p4-sealed-holdout-scoring":
        raise P4VerificationError("manifest scope mismatch")
    if manifest.get("status") != expected_status:
        raise P4VerificationError("manifest status mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        target = output_dir / name
        seen.add(name)
        if not target.is_file():
            raise P4VerificationError(f"manifest file missing: {name}")
        if target.stat().st_size != int(record["size_bytes"]):
            raise P4VerificationError(f"manifest size mismatch: {name}")
        if file_sha256(target) != record["sha256"]:
            raise P4VerificationError(f"manifest hash mismatch: {name}")
    expected = {
        item.name
        for item in output_dir.iterdir()
        if item.is_file()
        and item.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise P4VerificationError("manifest coverage mismatch")


def verify_p4(
    output_dir: Path,
    request: HoldoutScoringRequest,
    lock: dict[str, Any],
    *,
    formal: bool = True,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    expected = score_holdout(request, lock, formal=formal)
    response = _load_json(output_dir / "response.json")
    if response.get("status") != expected["status"]:
        raise P4VerificationError("response status mismatch")
    if response.get("scoring_scope") != "SEALED_PREDICTIONS_ONLY":
        raise P4VerificationError("scoring scope mismatch")
    if response.get("model_execution") is not False:
        raise P4VerificationError("P4 unexpectedly claims model execution")
    if response.get("retraining") is not False:
        raise P4VerificationError("P4 unexpectedly claims retraining")
    if response.get("reprediction") is not False:
        raise P4VerificationError("P4 unexpectedly claims reprediction")
    if response.get("promotion_status") != (
        "HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED"
    ):
        raise P4VerificationError("Holdout result was incorrectly promoted")
    if formal and response.get("status") != "PASS":
        raise P4VerificationError("formal P4 requires every locked row to PASS")

    if _load_json(output_dir / "REQUEST_METADATA.json") != _request_metadata(
        request
    ):
        raise P4VerificationError("request metadata mismatch")
    if _load_json(output_dir / "P3_LINEAGE.json") != expected[
        "prediction_lock_lineage"
    ]:
        raise P4VerificationError("P3 lineage mismatch")
    if _load_json(output_dir / "HOLDOUT_ACTUALS.json") != request.actuals.model_dump(
        mode="json"
    ):
        raise P4VerificationError("Holdout actuals mismatch")
    if _load_json(output_dir / "HOLDOUT_RESULTS.json") != expected[
        "holdout_results"
    ]:
        raise P4VerificationError("Holdout result metrics mismatch")
    if _load_json(
        output_dir / "HOLDOUT_CANDIDATE_AGGREGATES.json"
    ) != expected["candidate_aggregates"]:
        raise P4VerificationError("Holdout candidate aggregates mismatch")
    if _load_json(output_dir / "HOLDOUT_LEADERBOARD.json") != expected[
        "leaderboard"
    ]:
        raise P4VerificationError("Holdout leaderboard mismatch")
    if _load_json(output_dir / "BASELINE_COMPARISON.json") != expected[
        "baseline_comparison"
    ]:
        raise P4VerificationError("baseline comparison mismatch")

    _verify_manifest(output_dir, expected_status=expected["status"])
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p4-sealed-holdout-scoring",
        "holdout_scoring_status": expected["status"],
        "candidate_result_count": len(expected["holdout_results"]),
        "candidate_aggregate_count": len(expected["candidate_aggregates"]),
        "selected_oof_candidate_id": expected["selected_oof_candidate_id"],
        "scoring_scope": "SEALED_PREDICTIONS_ONLY",
        "model_execution": False,
        "retraining": False,
        "reprediction": False,
        "promotion_status": expected["promotion_status"],
    }
