"""Resume-safe OFAT coarse trials for the isolated Bingo5 parameter pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS
from loto.evaluation.protocol_v2 import canonical_sha256, write_protocol_artifact
from loto.evaluation.unified_campaign import (
    UnifiedCampaignConfig,
    _evaluate_candidate,
    _prepare_game,
)
from loto.models.catalog_full import build_catalog

from .artifacts import atomic_write_json, canonical_json_bytes
from .contracts import ModelInventoryRow, ModelSearchSpace, SearchSpaceStatus


def _parameter_hash(params: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(params)).hexdigest()


def build_ofat_trials(space: ModelSearchSpace) -> list[dict[str, Any]]:
    """Return the baseline plus one-parameter-at-a-time treatments."""

    if space.status is not SearchSpaceStatus.READY:
        return []
    baseline = dict(space.baseline_params)
    missing = [dimension.parameter for dimension in space.dimensions if dimension.parameter not in baseline]
    if missing:
        raise ValueError(
            f"READY search space lacks auditable baseline values for {space.model_id}: {missing}"
        )

    trials: list[dict[str, Any]] = [
        {
            "kind": "baseline",
            "parameter": None,
            "value": None,
            "params": baseline,
        }
    ]
    for dimension in space.dimensions:
        anchor = baseline[dimension.parameter]
        for value in dimension.values:
            if value == anchor:
                continue
            params = dict(baseline)
            params[dimension.parameter] = value
            trials.append(
                {
                    "kind": "treatment",
                    "parameter": dimension.parameter,
                    "value": value,
                    "params": params,
                }
            )
    if len(trials) > space.trial_budget:
        raise AssertionError(
            f"generated OFAT trials exceed approved budget for {space.model_id}: "
            f"{len(trials)}>{space.trial_budget}"
        )
    return trials


def _prediction_values_sha256(result: dict[str, Any]) -> str | None:
    seed_results = result.get("seed_results", [])
    if len(seed_results) != 1:
        return None
    lock = seed_results[0].get("prediction_lock")
    if not isinstance(lock, dict):
        return None
    path = Path(str(lock.get("path", "")))
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions = payload.get("predictions")
    if not isinstance(predictions, list):
        return None
    return hashlib.sha256(canonical_json_bytes(predictions)).hexdigest()


def _metric(result: dict[str, Any], metric: str, field: str = "mean") -> float | None:
    try:
        return float(result["seed_summary"][metric][field])
    except (KeyError, TypeError, ValueError):
        return None


def _trial_checkpoint_path(root: Path, model_id: str, digest: str) -> Path:
    safe = model_id.replace("/", "_").replace(":", "_")
    return root / "trials" / safe / f"{digest}.json"


def _load_checkpoint(path: Path, contract_sha256: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract_sha256") != contract_sha256:
        raise RuntimeError(f"trial checkpoint contract mismatch: {path}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"trial checkpoint result is invalid: {path}")
    expected = payload.get("result_sha256")
    if expected != canonical_sha256(result):
        raise RuntimeError(f"trial checkpoint result hash mismatch: {path}")
    return result


def _cleanup_incomplete_prediction_lock(output: Path, trial_id: str) -> None:
    from loto.evaluation.path_codec import encode_path_component

    root = (output / "prediction_locks").resolve()
    path = (root / "bingo5" / encode_path_component(trial_id)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"unsafe prediction-lock cleanup path: {path}") from exc
    if path.exists():
        shutil.rmtree(path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False))
            handle.write("\n")
        handle.flush()
    temp.replace(path)


def _effectiveness(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_model.setdefault(str(row["model_id"]), []).append(row)

    output: list[dict[str, Any]] = []
    for model_id, model_rows in sorted(by_model.items()):
        baseline_rows = [row for row in model_rows if row["kind"] == "baseline"]
        if len(baseline_rows) != 1:
            continue
        baseline = baseline_rows[0]
        baseline_hash = baseline.get("prediction_values_sha256")
        parameters = sorted(
            {str(row["parameter"]) for row in model_rows if row.get("parameter") is not None}
        )
        for parameter in parameters:
            treatments = [row for row in model_rows if row.get("parameter") == parameter]
            successful = [
                row
                for row in treatments
                if row.get("status") == "SUCCEEDED" and row.get("prediction_values_sha256")
            ]
            changed = [
                row
                for row in successful
                if baseline_hash is not None and row["prediction_values_sha256"] != baseline_hash
            ]
            if not successful or baseline.get("status") != "SUCCEEDED":
                verdict = "INCONCLUSIVE"
            elif changed:
                verdict = "EFFECTIVE_PARAMETER"
            else:
                verdict = "INEFFECTIVE_PARAMETER"
            output.append(
                {
                    "model_id": model_id,
                    "parameter": parameter,
                    "verdict": verdict,
                    "baseline_prediction_hash": baseline_hash,
                    "treatments_total": len(treatments),
                    "treatments_succeeded": len(successful),
                    "treatments_changed_prediction": len(changed),
                    "treatment_values": [row.get("value") for row in treatments],
                }
            )
    return output


def _ranking(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    succeeded = [row for row in rows if row.get("status") == "SUCCEEDED"]
    succeeded.sort(
        key=lambda row: (
            -float(row.get("hit_at_1") or -1.0),
            -float(row.get("all_positions_hit_at_1") or -1.0),
            float(row.get("mae") if row.get("mae") is not None else float("inf")),
            str(row["model_id"]),
            str(row["parameter_hash"]),
        )
    )
    ranking: list[dict[str, Any]] = []
    best: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(succeeded, start=1):
        ranked = {"rank": index, **row}
        ranking.append(ranked)
        best.setdefault(str(row["model_id"]), ranked)
    return ranking, best


def run_coarse_ofat(
    frame: pd.DataFrame,
    inventory: list[ModelInventoryRow],
    spaces: list[ModelSearchSpace],
    *,
    run_root: Path,
    input_sha256: str,
    git_commit: str,
    device: str = "auto",
    precision: str = "32",
    max_steps: int = 5,
    wall_time_seconds: int = 600,
    gpu_count: int = 0,
    gpu_memory_bytes: int = 0,
) -> dict[str, Any]:
    """Execute bounded one-factor screening with strict trial checkpoints."""

    coarse_root = run_root.resolve() / "coarse"
    output = coarse_root / "artifacts"
    checkpoint = coarse_root / "checkpoints"
    output.mkdir(parents=True, exist_ok=True)
    checkpoint.mkdir(parents=True, exist_ok=True)

    ready = [space for space in spaces if space.status is SearchSpaceStatus.READY]
    contract = {
        "schema_version": "bingo5-coarse-ofat-contract-v1",
        "git_commit": git_commit,
        "input_sha256": input_sha256,
        "target_game": "bingo5",
        "seed": 42,
        "folds": 1,
        "test_size": 20,
        "min_train_size": 100,
        "holdout": "CLOSED",
        "prospective": "CLOSED",
        "promotion": "CLOSED",
        "device": device,
        "precision": precision,
        "max_steps": max_steps,
        "wall_time_seconds": wall_time_seconds,
        "search_spaces_sha256": canonical_sha256(
            [space.model_dump(mode="json") for space in spaces]
        ),
    }
    contract_sha = canonical_sha256(contract)
    contract_path = checkpoint / "contract.json"
    envelope = {"contract_sha256": contract_sha, "contract": contract}
    if contract_path.exists():
        stored = json.loads(contract_path.read_text(encoding="utf-8"))
        if stored != envelope:
            raise RuntimeError("coarse checkpoint contract mismatch; refusing resume")
    else:
        atomic_write_json(contract_path, envelope)

    config = UnifiedCampaignConfig(
        output_dir=output,
        git_commit=git_commit,
        games=("bingo5",),
        seeds=(42,),
        folds=1,
        test_size=20,
        min_train_size=100,
        holdout_size=0,
        gap=0,
        device=device,
        precision=precision,
        max_trials=1,
        parallel_trials=1,
        wall_time_seconds=wall_time_seconds,
        max_steps=max_steps,
        gpu_count=gpu_count,
        gpu_memory_bytes=gpu_memory_bytes,
    )
    prepared = _prepare_game("bingo5", frame, config)
    protocol_path = output / "protocols" / "bingo5.json"
    if not protocol_path.exists():
        write_protocol_artifact(protocol_path, prepared.protocol)

    baseline_results: list[dict[str, Any]] = []
    baseline_path = checkpoint / "baselines.json"
    if baseline_path.exists():
        stored = json.loads(baseline_path.read_text(encoding="utf-8"))
        if stored.get("contract_sha256") != contract_sha:
            raise RuntimeError("baseline checkpoint contract mismatch")
        baseline_results = list(stored["results"])
    else:
        for baseline_id in REQUIRED_BASELINE_IDS:
            baseline_results.append(
                _evaluate_candidate(
                    prepared,
                    config,
                    candidate_id=f"coarse-baseline:{baseline_id}",
                    source="baseline",
                    library="baseline",
                    task="position",
                    baseline_id=baseline_id,
                )
            )
        atomic_write_json(
            baseline_path,
            {"contract_sha256": contract_sha, "results": baseline_results},
        )

    entry_by_id = {entry.model_id: entry for entry in build_catalog()}
    inventory_by_id = {row.model_id: row for row in inventory}
    trial_rows: list[dict[str, Any]] = []
    for space in ready:
        entry = entry_by_id.get(space.model_id)
        if entry is None:
            raise RuntimeError(f"READY model is not in broad catalog: {space.model_id}")
        if space.model_id not in inventory_by_id:
            raise RuntimeError(f"READY model is missing inventory row: {space.model_id}")
        for trial in build_ofat_trials(space):
            params = dict(trial["params"])
            digest = _parameter_hash(params)
            trial_id = f"{space.model_id}@{digest[:16]}"
            trial_checkpoint = _trial_checkpoint_path(checkpoint, space.model_id, digest)
            if trial_checkpoint.exists():
                result = _load_checkpoint(trial_checkpoint, contract_sha)
            else:
                _cleanup_incomplete_prediction_lock(output, trial_id)
                sweep_entry = replace(
                    entry,
                    model_id=f"{entry.model_id}__sweep__{digest[:16]}",
                    default_params=params,
                )
                result = _evaluate_candidate(
                    prepared,
                    config,
                    candidate_id=trial_id,
                    source="parameter_sweep",
                    library=entry.library,
                    task=entry.task,
                    entry=sweep_entry,
                )
                trial_checkpoint.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(
                    trial_checkpoint,
                    {
                        "contract_sha256": contract_sha,
                        "result_sha256": canonical_sha256(result),
                        "result": result,
                    },
                )

            trial_rows.append(
                {
                    "model_id": space.model_id,
                    "trial_id": trial_id,
                    "kind": trial["kind"],
                    "parameter": trial["parameter"],
                    "value": trial["value"],
                    "requested_params": params,
                    "resolved_params": params,
                    "constructor_params": params,
                    "parameter_hash": digest,
                    "status": result.get("status"),
                    "reason": result.get("reason", ""),
                    "hit_at_1": _metric(result, "hit_at_1"),
                    "position_hit_at_1": _metric(result, "position_hit_at_1"),
                    "all_positions_hit_at_1": _metric(result, "all_positions_hit_at_1"),
                    "mae": _metric(result, "mae"),
                    "mse": _metric(result, "mse"),
                    "rmse": _metric(result, "rmse"),
                    "prediction_values_sha256": _prediction_values_sha256(result),
                    "failures": result.get("failures", []),
                }
            )

    effectiveness = _effectiveness(trial_rows)
    ranking, best = _ranking(trial_rows)
    atomic_write_json(run_root / "BASELINE_RESULTS.json", baseline_results)
    atomic_write_json(run_root / "PARAMETER_EFFECTIVENESS.json", effectiveness)
    atomic_write_json(run_root / "MODEL_BEST_PARAMS.json", best)
    _write_jsonl(run_root / "TRIALS.jsonl", trial_rows)

    flat_rows = [
        {
            key: value
            for key, value in row.items()
            if key not in {"requested_params", "resolved_params", "constructor_params", "failures"}
        }
        for row in trial_rows
    ]
    frame_rows = pd.DataFrame(flat_rows)
    frame_rows.to_parquet(run_root / "TRIALS.parquet", index=False)
    pd.DataFrame(ranking).to_csv(run_root / "MODEL_RANKING.csv", index=False)
    pd.DataFrame(ranking).to_parquet(run_root / "MODEL_RANKING.parquet", index=False)
    return {
        "ready_models": len(ready),
        "trials": len(trial_rows),
        "succeeded": sum(1 for row in trial_rows if row["status"] == "SUCCEEDED"),
        "failed": sum(1 for row in trial_rows if row["status"] != "SUCCEEDED"),
        "parameter_effectiveness": effectiveness,
        "best": best,
        "contract_sha256": contract_sha,
    }
