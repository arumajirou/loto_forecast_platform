"""Restart-safe orchestration for the TAJ-21 development-only unified campaign.

Checkpoints live outside the formal artifact directory. A checkpoint is reusable only
when its run contract, model/game identity, result hash, and every referenced Prediction
Lock still match exactly. Any corrupt or mismatched durable checkpoint fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS, REQUIRED_POINT_METRICS
from loto.evaluation.path_codec import encode_path_component
from loto.evaluation.protocol_v2 import (
    canonical_json_bytes,
    canonical_sha256,
    write_protocol_artifact,
)
from loto.evaluation.unified_campaign import (
    CAMPAIGN_SCHEMA_VERSION,
    UnifiedCampaignConfig,
    _evaluate_candidate,
    _leaderboards,
    _macro_summary,
    _prepare_game,
    _resolved_code_hash,
    _selected_entries,
    _selected_probabilistic_routes,
    build_campaign_plan,
)

RESUME_CONTRACT_SCHEMA_VERSION = "taj21-resume-contract-v1"
UNIT_CHECKPOINT_SCHEMA_VERSION = "taj21-model-game-checkpoint-v1"


class UnifiedCampaignResumeConfig(BaseModel):
    """Immutable runtime evidence required to reuse TAJ-21 unit checkpoints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint_dir: Path
    input_sha256: dict[str, str]

    @field_validator("input_sha256")
    @classmethod
    def validate_input_sha256(cls, value: dict[str, str]) -> dict[str, str]:
        for game, digest in value.items():
            if not game:
                raise ValueError("input_sha256 game keys must be non-empty")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"input_sha256[{game}] must be a lowercase SHA-256 digest")
        return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        output[key] = value
    return output


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant is forbidden: {value}")
            ),
        )
    except Exception as exc:
        raise ValueError(f"corrupt checkpoint JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"checkpoint JSON must contain an object: {path}")
    return payload


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(payload) + b"\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _contract_payload(
    config: UnifiedCampaignConfig,
    *,
    resume: UnifiedCampaignResumeConfig,
    plan: list[dict[str, str]],
) -> dict[str, Any]:
    expected_games = set(config.games)
    observed_games = set(resume.input_sha256)
    if observed_games != expected_games:
        raise ValueError(
            "resume input_sha256 must exactly cover configured games: "
            f"expected={sorted(expected_games)} observed={sorted(observed_games)}"
        )
    model_ids = sorted({row["candidate_id"] for row in plan})
    return {
        "schema_version": RESUME_CONTRACT_SCHEMA_VERSION,
        "git_commit": config.git_commit,
        "code_hash": _resolved_code_hash(config),
        "output_dir": str(config.output_dir.resolve()),
        "checkpoint_dir": str(resume.checkpoint_dir.resolve()),
        "input_sha256": {game: resume.input_sha256[game] for game in config.games},
        "config": config.model_dump(mode="json"),
        "plan_sha256": canonical_sha256(plan),
        "model_ids": model_ids,
        "model_count": len(model_ids),
        "baseline_ids": list(REQUIRED_BASELINE_IDS),
        "seeds": list(config.seeds),
        "folds": config.folds,
        "test_size": config.test_size,
        "min_train_size": config.min_train_size,
        "holdout_size": config.holdout_size,
        "gap": config.gap,
        "tau": config.tau,
        "feature_windows": list(config.feature_windows),
    }


def _bind_resume_contract(
    config: UnifiedCampaignConfig,
    *,
    resume: UnifiedCampaignResumeConfig,
    plan: list[dict[str, str]],
) -> str:
    output = config.output_dir.resolve()
    checkpoint_dir = resume.checkpoint_dir.resolve()
    try:
        checkpoint_dir.relative_to(output)
    except ValueError:
        pass
    else:
        raise ValueError("checkpoint_dir must be outside the formal campaign output directory")

    contract_path = checkpoint_dir / "contract.json"
    payload = _contract_payload(config, resume=resume, plan=plan)
    digest = canonical_sha256(payload)
    envelope = {
        "schema_version": RESUME_CONTRACT_SCHEMA_VERSION,
        "contract_sha256": digest,
        "contract": payload,
    }

    if contract_path.exists():
        stored = _read_json(contract_path)
        if stored.get("schema_version") != RESUME_CONTRACT_SCHEMA_VERSION:
            raise RuntimeError("resume contract schema mismatch")
        if stored.get("contract_sha256") != digest:
            raise RuntimeError("resume contract SHA mismatch")
        if stored.get("contract") != payload:
            raise RuntimeError("resume contract payload mismatch")
        if canonical_sha256(stored["contract"]) != stored["contract_sha256"]:
            raise RuntimeError("resume contract is internally corrupt")
        return digest

    if output.exists():
        raise FileExistsError(
            f"formal output exists without a matching resume contract; refusing reuse: {output}"
        )
    if checkpoint_dir.exists() and any(checkpoint_dir.iterdir()):
        raise RuntimeError(
            "checkpoint directory contains data without a durable contract; refusing reuse: "
            f"{checkpoint_dir}"
        )
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(contract_path, envelope)
    return digest


def _ensure_protocol_artifact(path: Path, protocol: Any) -> None:
    artifact = {
        "protocol_hash": protocol.protocol_hash,
        "comparison_budget_hash": protocol.comparison_budget_hash,
        "protocol": protocol.canonical_payload(),
    }
    expected = canonical_json_bytes(artifact) + b"\n"
    if path.exists():
        if path.read_bytes() != expected:
            raise RuntimeError(f"existing protocol artifact mismatches current contract: {path}")
        return
    write_protocol_artifact(path, protocol)


def _unit_identity(
    *,
    game: str,
    candidate_id: str,
    source: str,
    library: str,
    task: str,
) -> dict[str, str]:
    return {
        "game": game,
        "candidate_id": candidate_id,
        "source": source,
        "library": library,
        "task": task,
    }


def _unit_checkpoint_path(
    resume: UnifiedCampaignResumeConfig,
    *,
    game: str,
    candidate_id: str,
) -> Path:
    return (
        resume.checkpoint_dir.resolve()
        / "units"
        / encode_path_component(game)
        / f"{encode_path_component(candidate_id)}.json"
    )


def _prediction_lock_dir(
    config: UnifiedCampaignConfig,
    *,
    game: str,
    candidate_id: str,
) -> Path:
    return config.output_dir / "prediction_locks" / game / encode_path_component(candidate_id)


def _discard_incomplete_unit_locks(
    config: UnifiedCampaignConfig,
    *,
    game: str,
    candidate_id: str,
) -> None:
    lock_dir = _prediction_lock_dir(config, game=game, candidate_id=candidate_id)
    if not lock_dir.exists():
        return
    root = (config.output_dir / "prediction_locks").resolve()
    resolved = lock_dir.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"refusing unsafe Prediction Lock cleanup path: {resolved}") from exc
    shutil.rmtree(resolved)


def _verify_prediction_locks(
    result: Mapping[str, Any],
    config: UnifiedCampaignConfig,
) -> None:
    game = str(result["game"])
    candidate_id = str(result["candidate_id"])
    protocol_hash = str(result["protocol_hash"])
    for seed_result in result.get("seed_results", []):
        if not isinstance(seed_result, dict):
            raise RuntimeError("checkpoint seed_results must contain objects")
        seed = int(seed_result["seed"])
        lock = seed_result.get("prediction_lock")
        if not isinstance(lock, dict):
            raise RuntimeError(
                "checkpointed seed result is missing Prediction Lock metadata: "
                f"{game}/{candidate_id}/seed={seed}"
            )
        expected_path = (
            _prediction_lock_dir(config, game=game, candidate_id=candidate_id) / f"seed-{seed}.json"
        ).resolve()
        stored_path = Path(str(lock.get("path", ""))).resolve()
        if stored_path != expected_path:
            raise RuntimeError(
                f"Prediction Lock path mismatch for {game}/{candidate_id}/seed={seed}"
            )
        if not stored_path.is_file():
            raise RuntimeError(f"Prediction Lock missing: {stored_path}")
        data = stored_path.read_bytes()
        actual_sha = hashlib.sha256(data).hexdigest()
        if lock.get("sha256") != actual_sha:
            raise RuntimeError(f"Prediction Lock SHA mismatch: {stored_path}")
        if "bytes" in lock and int(lock["bytes"]) != len(data):
            raise RuntimeError(f"Prediction Lock byte count mismatch: {stored_path}")
        payload = _read_json(stored_path)
        if payload.get("game") != game:
            raise RuntimeError(f"Prediction Lock game mismatch: {stored_path}")
        if payload.get("candidate_id") != candidate_id:
            raise RuntimeError(f"Prediction Lock candidate mismatch: {stored_path}")
        if int(payload.get("seed", -1)) != seed:
            raise RuntimeError(f"Prediction Lock seed mismatch: {stored_path}")
        if payload.get("protocol_hash") != protocol_hash:
            raise RuntimeError(f"Prediction Lock protocol mismatch: {stored_path}")
        if payload.get("actuals_known") is not False:
            raise RuntimeError(f"Prediction Lock actuals_known contract violated: {stored_path}")
        if lock.get("sealed_at_utc") and payload.get("sealed_at_utc") != lock.get("sealed_at_utc"):
            raise RuntimeError(f"Prediction Lock timestamp mismatch: {stored_path}")


def _load_unit_checkpoint(
    path: Path,
    *,
    contract_sha256: str,
    unit: dict[str, str],
    config: UnifiedCampaignConfig,
) -> dict[str, Any]:
    stored = _read_json(path)
    if stored.get("schema_version") != UNIT_CHECKPOINT_SCHEMA_VERSION:
        raise RuntimeError(f"unit checkpoint schema mismatch: {path}")
    if stored.get("contract_sha256") != contract_sha256:
        raise RuntimeError(f"unit checkpoint contract mismatch: {path}")
    if stored.get("unit") != unit:
        raise RuntimeError(f"unit checkpoint identity mismatch: {path}")
    result = stored.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"unit checkpoint result is missing: {path}")
    if canonical_sha256(result) != stored.get("result_sha256"):
        raise RuntimeError(f"unit checkpoint result SHA mismatch: {path}")
    for key in ("game", "candidate_id", "source", "library", "task"):
        if result.get(key) != unit[key]:
            raise RuntimeError(f"unit checkpoint result {key} mismatch: {path}")
    _verify_prediction_locks(result, config)
    return result


def _write_unit_checkpoint(
    path: Path,
    *,
    contract_sha256: str,
    unit: dict[str, str],
    result: dict[str, Any],
) -> None:
    envelope = {
        "schema_version": UNIT_CHECKPOINT_SCHEMA_VERSION,
        "contract_sha256": contract_sha256,
        "unit": unit,
        "result_sha256": canonical_sha256(result),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "result": result,
    }
    _atomic_write_json(path, envelope)


def _execute_or_resume_unit(
    *,
    prepared: Any,
    config: UnifiedCampaignConfig,
    resume: UnifiedCampaignResumeConfig,
    contract_sha256: str,
    candidate_id: str,
    source: str,
    library: str,
    task: str,
    baseline_id: str | None = None,
    entry: Any | None = None,
    probabilistic_route: Any | None = None,
) -> dict[str, Any]:
    game = prepared.geometry.key
    unit = _unit_identity(
        game=game,
        candidate_id=candidate_id,
        source=source,
        library=library,
        task=task,
    )
    checkpoint = _unit_checkpoint_path(resume, game=game, candidate_id=candidate_id)
    if checkpoint.exists():
        return _load_unit_checkpoint(
            checkpoint,
            contract_sha256=contract_sha256,
            unit=unit,
            config=config,
        )

    # No durable checkpoint means the unit was never completed. Any locks below this
    # exact unit path are remnants of an interrupted attempt and must not be mixed in.
    _discard_incomplete_unit_locks(config, game=game, candidate_id=candidate_id)
    result = _evaluate_candidate(
        prepared,
        config,
        candidate_id=candidate_id,
        source=source,
        library=library,
        task=task,
        baseline_id=baseline_id,
        entry=entry,
        probabilistic_route=probabilistic_route,
    )
    _write_unit_checkpoint(
        checkpoint,
        contract_sha256=contract_sha256,
        unit=unit,
        result=result,
    )
    return result


def _finalize_campaign(
    *,
    config: UnifiedCampaignConfig,
    results: list[dict[str, Any]],
    entries: list[Any],
    probabilistic_ids: set[str],
    expected_pairs: int,
) -> dict[str, Any]:
    catalog_results = [row for row in results if row["source"] in {"catalog", "probabilistic"}]
    if len(catalog_results) != expected_pairs:
        raise AssertionError("result matrix lost one or more model/game combinations")
    pair_keys = {(row["game"], row["candidate_id"]) for row in catalog_results}
    if len(pair_keys) != expected_pairs:
        raise AssertionError("result matrix contains duplicate or missing model/game pairs")

    leaderboards = _leaderboards(results, config.games)
    macro = _macro_summary(results, config.games)
    status_counts: dict[str, int] = {}
    for row in catalog_results:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    unified_models = len(entries) + len(probabilistic_ids)
    summary = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "status": (
            "SUCCEEDED" if status_counts.get("SUCCEEDED", 0) == expected_pairs else "PARTIAL"
        ),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": config.git_commit,
        "code_hash": _resolved_code_hash(config),
        "games": list(config.games),
        "catalog_models": unified_models,
        "broad_catalog_models": len(entries),
        "probabilistic_catalog_models": len(probabilistic_ids),
        "expected_model_game_pairs": expected_pairs,
        "observed_model_game_pairs": len(catalog_results),
        "matrix_complete": len(catalog_results) == expected_pairs
        and len(pair_keys) == expected_pairs,
        "status_counts": status_counts,
        "primary_metric": "hit_at_1",
        "required_metrics": list(REQUIRED_POINT_METRICS),
        "required_baselines": list(REQUIRED_BASELINE_IDS),
        "seeds": list(config.seeds),
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "results": results,
        "leaderboards": leaderboards,
        "macro_summary": macro,
    }
    output = config.output_dir
    (output / "campaign_summary.json").write_bytes(canonical_json_bytes(summary) + b"\n")

    flat_rows: list[dict[str, Any]] = []
    for row in results:
        flat = {
            "game": row["game"],
            "candidate_id": row["candidate_id"],
            "source": row["source"],
            "library": row["library"],
            "task": row["task"],
            "status": row["status"],
            "reason": row.get("reason", ""),
            "protocol_hash": row["protocol_hash"],
        }
        for metric_id in REQUIRED_POINT_METRICS:
            summary_item = row.get("seed_summary", {}).get(metric_id)
            flat[f"{metric_id}_mean"] = summary_item["mean"] if summary_item else None
            flat[f"{metric_id}_variance"] = (
                summary_item["population_variance"] if summary_item else None
            )
            flat[f"{metric_id}_worst"] = summary_item["worst_value"] if summary_item else None
            flat[f"{metric_id}_worst_seed"] = summary_item["worst_seed"] if summary_item else None
        flat_rows.append(flat)
    pd.DataFrame(flat_rows).to_csv(output / "model_game_results.csv", index=False)
    pd.DataFrame(macro).to_csv(output / "all_game_macro_summary.csv", index=False)

    artifact_paths = sorted(
        path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    checksum_lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}"
        for path in artifact_paths
    ]
    (output / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="utf-8",
    )
    return summary


def run_resumable_unified_campaign(
    frames: Mapping[str, pd.DataFrame],
    config: UnifiedCampaignConfig,
    *,
    resume: UnifiedCampaignResumeConfig,
) -> dict[str, Any]:
    """Run TAJ-21 with atomic model/game checkpoints and strict resume validation."""

    entries = _selected_entries(config)
    probabilistic_routes = _selected_probabilistic_routes(config)
    probabilistic_ids = {route.model_id for route in probabilistic_routes}
    plan = build_campaign_plan(config)
    unified_models = len(entries) + len(probabilistic_ids)
    expected_pairs = unified_models * len(config.games)
    if len(plan) != expected_pairs:
        raise AssertionError("campaign plan does not cover every requested model/game pair")

    contract_sha256 = _bind_resume_contract(config, resume=resume, plan=plan)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    prepared: dict[str, Any] = {}
    for game in config.games:
        if game not in frames:
            raise KeyError(f"missing input frame for game={game}")
        prepared[game] = _prepare_game(game, frames[game], config)
        _ensure_protocol_artifact(
            config.output_dir / "protocols" / f"{game}.json",
            prepared[game].protocol,
        )

    results: list[dict[str, Any]] = []
    for game in config.games:
        context = prepared[game]
        for baseline_id in REQUIRED_BASELINE_IDS:
            results.append(
                _execute_or_resume_unit(
                    prepared=context,
                    config=config,
                    resume=resume,
                    contract_sha256=contract_sha256,
                    candidate_id=f"baseline:{baseline_id}",
                    source="baseline",
                    library="baseline",
                    task="position",
                    baseline_id=baseline_id,
                )
            )
        for entry in entries:
            results.append(
                _execute_or_resume_unit(
                    prepared=context,
                    config=config,
                    resume=resume,
                    contract_sha256=contract_sha256,
                    candidate_id=entry.model_id,
                    source="catalog",
                    library=entry.library,
                    task=entry.task,
                    entry=entry,
                )
            )
        for route in probabilistic_routes:
            if route.game != game:
                continue
            results.append(
                _execute_or_resume_unit(
                    prepared=context,
                    config=config,
                    resume=resume,
                    contract_sha256=contract_sha256,
                    candidate_id=route.model_id,
                    source="probabilistic",
                    library="probabilistic",
                    task=route.target_mode or "probabilistic",
                    probabilistic_route=route,
                )
            )

    return _finalize_campaign(
        config=config,
        results=results,
        entries=entries,
        probabilistic_ids=probabilistic_ids,
        expected_pairs=expected_pairs,
    )


__all__ = [
    "RESUME_CONTRACT_SCHEMA_VERSION",
    "UNIT_CHECKPOINT_SCHEMA_VERSION",
    "UnifiedCampaignResumeConfig",
    "run_resumable_unified_campaign",
]
