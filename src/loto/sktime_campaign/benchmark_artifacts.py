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
    ValidationBenchmarkRequest,
    aggregate_seed_results,
    build_leaderboard,
    compute_metrics,
    data_contract,
    run_validation_benchmark,
    split_views,
)


class BenchmarkVerificationError(RuntimeError):
    """Raised when P2 benchmark evidence fails closed verification."""


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
        raise BenchmarkVerificationError(f"unable to read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_metadata(request: ValidationBenchmarkRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload["dataset"] = {
        **payload["dataset"],
        "values": "REDACTED_NOT_COPIED_TO_ARTIFACTS",
    }
    return payload


def _write_manifest_and_sha(output_dir: Path, *, status: str) -> None:
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": status,
        "scope": "sktime-p2-chronological-validation",
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


def persist_validation_benchmark(request: ValidationBenchmarkRequest) -> dict[str, Any]:
    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise RuntimeError(f"output directory must be empty: {output_dir}")

    result = run_validation_benchmark(request)
    response = {
        "schema_version": "1.0",
        "status": result["status"],
        "operation": request.operation,
        "environment_lane": request.environment_lane,
        "expected_sktime_version": request.expected_sktime_version,
        "stage": "validation",
        "best_validation_candidate": result["best_validation_candidate"],
        "promotion_status": result["promotion_status"],
        "candidate_result_count": len(result["candidate_results"]),
    }
    _write_json(output_dir / "REQUEST_METADATA.json", _request_metadata(request))
    _write_json(output_dir / "DATA_CONTRACT.json", result["data_contract"])
    _write_json(output_dir / "VALIDATION_ACTUALS.json", result["actual_validation"])
    _write_json(output_dir / "CANDIDATE_RESULTS.json", result["candidate_results"])
    _write_json(output_dir / "SEED_AGGREGATES.json", result["seed_aggregates"])
    _write_json(output_dir / "LEADERBOARD.json", result["leaderboard"])
    _write_json(output_dir / "response.json", response)
    _write_manifest_and_sha(output_dir, status=result["status"])
    return response


def _verify_sha256sums(output_dir: Path) -> None:
    sums_path = output_dir / "SHA256SUMS"
    if not sums_path.is_file():
        raise BenchmarkVerificationError("missing SHA256SUMS")
    seen: set[str] = set()
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        expected, relative_name = line.split("  ", maxsplit=1)
        if relative_name in seen:
            raise BenchmarkVerificationError(f"duplicate SHA path: {relative_name}")
        seen.add(relative_name)
        path = output_dir / relative_name
        if not path.is_file() or _sha256(path) != expected:
            raise BenchmarkVerificationError(f"SHA-256 mismatch: {relative_name}")
    expected_files = {
        path.name for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise BenchmarkVerificationError("SHA256SUMS coverage mismatch")


def _verify_manifest(output_dir: Path, *, expected_status: str) -> None:
    manifest = _load_json(output_dir / "ARTIFACT_MANIFEST.json")
    if manifest.get("status") != expected_status:
        raise BenchmarkVerificationError("manifest status mismatch")
    seen: set[str] = set()
    for record in manifest.get("files", []):
        name = str(record["path"])
        path = output_dir / name
        seen.add(name)
        if not path.is_file():
            raise BenchmarkVerificationError(f"manifest file missing: {name}")
        if path.stat().st_size != int(record["size_bytes"]):
            raise BenchmarkVerificationError(f"manifest size mismatch: {name}")
        if _sha256(path) != record["sha256"]:
            raise BenchmarkVerificationError(f"manifest hash mismatch: {name}")
    expected = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    if seen != expected:
        raise BenchmarkVerificationError("manifest coverage mismatch")


def verify_validation_benchmark(
    output_dir: Path,
    request: ValidationBenchmarkRequest,
    *,
    formal: bool = True,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    response = _load_json(output_dir / "response.json")
    expected_status = str(response.get("status", ""))
    if expected_status not in {"PASS", "PARTIAL", "FAILED"}:
        raise BenchmarkVerificationError("invalid benchmark response status")
    if response.get("promotion_status") != "VALIDATION_ONLY_NOT_PROMOTED":
        raise BenchmarkVerificationError("validation result was incorrectly promoted")

    metadata = _load_json(output_dir / "REQUEST_METADATA.json")
    expected_metadata = _request_metadata(request)
    if metadata != expected_metadata:
        raise BenchmarkVerificationError("request metadata differs from supplied request")
    contract = _load_json(output_dir / "DATA_CONTRACT.json")
    if contract != data_contract(request):
        raise BenchmarkVerificationError("data contract mismatch")
    if contract.get("fit_scope") != "TRAIN_ONLY":
        raise BenchmarkVerificationError("fit scope is not Train-only")
    if contract.get("evaluation_scope") != "VALIDATION_ONLY":
        raise BenchmarkVerificationError("evaluation scope is not Validation-only")
    if contract.get("holdout_access") != "HASH_ONLY_NOT_SCORED":
        raise BenchmarkVerificationError("Holdout boundary is not hash-only")

    if formal:
        if request.baseline_ids != list(FORMAL_BASELINES):
            raise BenchmarkVerificationError("formal baseline inventory mismatch")
        if request.model_ids != list(FORMAL_MODELS):
            raise BenchmarkVerificationError("formal sktime model inventory mismatch")
        if request.random_seeds != [1, 2, 3]:
            raise BenchmarkVerificationError("formal random seeds must be [1, 2, 3]")

    views = split_views(request)
    actual = np.asarray(_load_json(output_dir / "VALIDATION_ACTUALS.json"), dtype=float)
    if not np.array_equal(actual, views["validation"]):
        raise BenchmarkVerificationError("persisted validation actuals mismatch")

    rows = _load_json(output_dir / "CANDIDATE_RESULTS.json")
    for row in rows:
        if row.get("fit_scope") != "TRAIN_ONLY":
            raise BenchmarkVerificationError("candidate used a non-Train fit scope")
        if row.get("evaluation_scope") != "VALIDATION_ONLY":
            raise BenchmarkVerificationError("candidate used a non-Validation score scope")
        if row.get("status") != "PASS":
            continue
        prediction = np.asarray(row.get("predictions"), dtype=float)
        expected_metrics = compute_metrics(
            actual,
            prediction,
            position_names=request.dataset.position_names,
        )
        if row.get("metrics") != expected_metrics:
            raise BenchmarkVerificationError(
                f"metrics mismatch for {row.get('candidate_id')} seed={row.get('seed')}"
            )

    aggregates = _load_json(output_dir / "SEED_AGGREGATES.json")
    expected_aggregates = aggregate_seed_results(rows)
    if aggregates != expected_aggregates:
        raise BenchmarkVerificationError("seed aggregates mismatch")
    leaderboard = _load_json(output_dir / "LEADERBOARD.json")
    if leaderboard != build_leaderboard(aggregates):
        raise BenchmarkVerificationError("leaderboard ordering mismatch")

    pass_count = sum(row.get("status") == "PASS" for row in rows)
    recalculated_status = (
        "PASS" if pass_count == len(rows) else ("PARTIAL" if pass_count else "FAILED")
    )
    if expected_status != recalculated_status:
        raise BenchmarkVerificationError("aggregate status mismatch")
    if formal and expected_status != "PASS":
        raise BenchmarkVerificationError("formal P2 requires every candidate to PASS")

    _verify_manifest(output_dir, expected_status=expected_status)
    _verify_sha256sums(output_dir)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-p2-chronological-validation",
        "benchmark_status": expected_status,
        "candidate_result_count": len(rows),
        "baseline_count": len(request.baseline_ids),
        "model_count": len(request.model_ids),
        "random_seeds": request.random_seeds,
        "primary_metric": "hit_at_1",
        "holdout_status": "HASH_ONLY_NOT_SCORED",
        "promotion_status": "VALIDATION_ONLY_NOT_PROMOTED",
    }
