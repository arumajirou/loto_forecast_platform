from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Final

from loto.game.geometry import known_games
from loto.probabilistic.catalog import list_probabilistic_model_specs
from loto.probabilistic.config import load_run_config
from loto.probabilistic.native_registry import list_native_implementations
from loto.probabilistic.planner import build_plan
from loto.probabilistic.runner import run_probabilistic

EXPECTED_PROBABILISTIC_MODELS: Final = 76
EXPECTED_GAMES: Final = 6
EXPECTED_PAIRS: Final = 456
KNOWN_RAW_FAILURES: Final = frozenset(
    {"INFERENCE_FAILED", "MODEL_BUILD_FAILED", "POSTERIOR_INVALID"}
)
NORMALIZED_STATUSES: Final = frozenset(
    {
        "RUNTIME_SMOKE_SUCCEEDED",
        "FAILED",
        "UNAVAILABLE",
        "NOT_ROUTABLE",
        "UNSUPPORTED_GAME",
        "TIMEOUT",
        "BLOCKED_GPU_RESOURCE",
    }
)


class Taj20MatrixError(RuntimeError):
    """Raised when the incremental probabilistic matrix cannot be certified."""


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise Taj20MatrixError(f"required JSON missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise Taj20MatrixError(f"required JSONL missing: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise Taj20MatrixError(f"JSONL row {number} is not an object: {path}")
        rows.append(payload)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise Taj20MatrixError(f"cannot resolve git HEAD: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _canonical_games() -> list[str]:
    games = list(known_games())
    if len(games) != EXPECTED_GAMES or len(set(games)) != EXPECTED_GAMES:
        raise Taj20MatrixError(
            "canonical game registry drift: "
            f"observed={len(games)} expected={EXPECTED_GAMES} games={games}"
        )
    return games


def _probabilistic_ids() -> list[str]:
    ids = [spec.model_id for spec in list_probabilistic_model_specs()]
    native_ids = [item.model_id for item in list_native_implementations()]
    if len(ids) != EXPECTED_PROBABILISTIC_MODELS or len(set(ids)) != EXPECTED_PROBABILISTIC_MODELS:
        raise Taj20MatrixError(
            "probabilistic registry drift: "
            f"observed={len(ids)} unique={len(set(ids))} expected={EXPECTED_PROBABILISTIC_MODELS}"
        )
    if set(ids) != set(native_ids):
        raise Taj20MatrixError(
            "probabilistic/native identity mismatch: "
            f"missing_native={sorted(set(ids) - set(native_ids))[:10]} "
            f"extra_native={sorted(set(native_ids) - set(ids))[:10]}"
        )
    return ids


def _base_config(*, output: Path, run_id: str, game: str, seed: int) -> Any:
    config = load_run_config("configs/probabilistic/native_smoke.yaml")
    return config.model_copy(
        update={
            "run_id": run_id,
            "games": [game],
            "output": str(output),
            "models": "all",
            "backend_policy": "primary_native",
            "backends": [],
            "seeds": [seed],
            "resume_policy": "disabled",
            "sealed_holdout": True,
            "speech_enabled": False,
            "email_enabled": False,
        }
    )


def build_matrix_plan(*, campaign_id: str, root: Path, seed: int) -> dict[str, Any]:
    model_ids = _probabilistic_ids()
    games = _canonical_games()
    tasks: list[dict[str, Any]] = []
    for game in games:
        config = _base_config(
            output=root / "ppl-runs",
            run_id=f"{campaign_id}-{game}",
            game=game,
            seed=seed,
        )
        trials = build_plan(config)
        if len(trials) != EXPECTED_PROBABILISTIC_MODELS:
            raise Taj20MatrixError(
                f"per-game planner did not preserve all model identities: game={game} "
                f"trials={len(trials)} expected={EXPECTED_PROBABILISTIC_MODELS}"
            )
        observed_ids = [trial.model_id for trial in trials]
        if (
            len(set(observed_ids)) != EXPECTED_PROBABILISTIC_MODELS
            or set(observed_ids) != set(model_ids)
        ):
            raise Taj20MatrixError(f"per-game model identity mismatch: game={game}")
        for trial in trials:
            tasks.append(
                {
                    "task_key": f"{trial.model_id}::{game}",
                    "model_id": trial.model_id,
                    "family": trial.family,
                    "game": game,
                    "planner_game": trial.game,
                    "target_mode": trial.target_mode,
                    "backend": trial.backend,
                    "inference_profile_id": trial.inference_profile_id,
                    "resource_class": trial.resource_class,
                    "allowed": trial.allowed,
                    "reason_code": trial.reason_code,
                    "details": list(trial.details),
                    "seed": trial.seed,
                    "source_trial_id": trial.trial_id,
                    "source_run_id": f"{campaign_id}-{game}",
                }
            )
    keys = [str(task["task_key"]) for task in tasks]
    if len(tasks) != EXPECTED_PAIRS or len(set(keys)) != EXPECTED_PAIRS:
        raise Taj20MatrixError(
            "incremental matrix mismatch: "
            f"rows={len(tasks)} unique={len(set(keys))} expected={EXPECTED_PAIRS}"
        )
    return {
        "schema_version": "taj20-probabilistic-matrix/v1",
        "issue": "TAJ-20 / GitHub #266",
        "source_head": _git_head(),
        "campaign_id": campaign_id,
        "seed": seed,
        "models": len(model_ids),
        "games": games,
        "expected_pairs": EXPECTED_PAIRS,
        "backend_policy": "primary_native",
        "runtime_profile": "configs/probabilistic/native_smoke.yaml",
        "tasks": tasks,
        "scientific_boundary": {
            "runtime_only": True,
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
    }


def _normalize_result(row: dict[str, Any], *, game: str, run_dir: Path) -> dict[str, Any]:
    raw = str(row.get("status", "")).upper()
    reason = str(row.get("reason_code", "")).upper()
    note: str | None = None
    if raw == "PASS":
        normalized = "RUNTIME_SMOKE_SUCCEEDED"
    elif raw == "BLOCKED":
        if reason == "TARGET_MODE_UNSUPPORTED":
            normalized = "UNSUPPORTED_GAME"
        elif reason in {
            "BACKEND_UNAVAILABLE",
            "DEPENDENCY_UNAVAILABLE",
            "NATIVE_BACKEND_UNAVAILABLE",
        }:
            normalized = "UNAVAILABLE"
        elif reason == "BLOCKED_GPU_RESOURCE":
            normalized = "BLOCKED_GPU_RESOURCE"
        else:
            normalized = "NOT_ROUTABLE"
    elif raw == "TIMEOUT":
        normalized = "TIMEOUT"
    elif raw in KNOWN_RAW_FAILURES:
        normalized = "FAILED"
    else:
        normalized = "FAILED"
        note = f"UNMAPPED_RAW_STATUS:{raw or '<empty>'}"
    model_id = str(row.get("model_id", ""))
    if not model_id:
        raise Taj20MatrixError(f"result missing model_id for game={game}")
    return {
        "task_key": f"{model_id}::{game}",
        "model_id": model_id,
        "family": row.get("family"),
        "game": game,
        "planner_game": row.get("game"),
        "target_mode": row.get("target_mode"),
        "backend": row.get("backend"),
        "raw_status": raw,
        "raw_reason": row.get("reason_code"),
        "normalized_status": normalized,
        "normalization_note": note,
        "source_trial_id": row.get("trial_id"),
        "source_run_dir": str(run_dir),
        "artifact_dir": row.get("artifact_dir"),
        "protocol_hash": row.get("protocol_hash"),
        "execution_fingerprint": row.get("execution_fingerprint"),
        "elapsed_seconds": row.get("elapsed_seconds"),
        "error": row.get("error"),
    }


def _source_result_complete(row: dict[str, Any]) -> bool:
    run_dir = Path(str(row.get("source_run_dir", "")))
    result_path = run_dir / "results.json"
    if not result_path.is_file():
        return False
    try:
        results = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    matches = [
        item
        for item in results
        if isinstance(item, dict)
        and str(item.get("model_id")) == str(row.get("model_id"))
        and str(item.get("trial_id")) == str(row.get("source_trial_id"))
    ]
    return len(matches) == 1 and str(matches[0].get("status", "")).upper() == str(
        row.get("raw_status", "")
    ).upper()


def verify_campaign(root: Path) -> dict[str, Any]:
    plan = _read_json(root / "MATRIX_PLAN.json")
    rows = _read_jsonl(root / "NORMALIZED_RESULTS.jsonl")
    expected_keys = {str(task["task_key"]) for task in plan.get("tasks", [])}
    observed_keys = [str(row.get("task_key", "")) for row in rows]
    duplicate_keys = sorted(key for key, count in Counter(observed_keys).items() if count != 1)
    missing_keys = sorted(expected_keys - set(observed_keys))
    unexpected_keys = sorted(set(observed_keys) - expected_keys)
    invalid_status = sorted(
        str(row.get("task_key"))
        for row in rows
        if str(row.get("normalized_status")) not in NORMALIZED_STATUSES
    )
    unmapped = sorted(
        str(row.get("task_key")) for row in rows if row.get("normalization_note")
    )
    missing_source_evidence = sorted(
        str(row.get("task_key")) for row in rows if not _source_result_complete(row)
    )
    model_ids = {str(row.get("model_id", "")) for row in rows}
    games = {str(row.get("game", "")) for row in rows}
    gates = {
        "plan_pairs_exact": len(expected_keys) == EXPECTED_PAIRS,
        "result_rows_exact": len(rows) == EXPECTED_PAIRS,
        "model_count_exact": len(model_ids) == EXPECTED_PROBABILISTIC_MODELS,
        "game_count_exact": len(games) == EXPECTED_GAMES,
        "no_duplicate_task_keys": not duplicate_keys,
        "no_missing_task_keys": not missing_keys,
        "no_unexpected_task_keys": not unexpected_keys,
        "normalized_status_taxonomy_valid": not invalid_status,
        "no_unmapped_raw_status": not unmapped,
        "all_rows_have_source_evidence": not missing_source_evidence,
        "holdout_closed": plan.get("scientific_boundary", {}).get("holdout") == "CLOSED",
        "prospective_closed": plan.get("scientific_boundary", {}).get("prospective") == "CLOSED",
        "promotion_closed": plan.get("scientific_boundary", {}).get("promotion") == "CLOSED",
    }
    counts = Counter(str(row.get("normalized_status")) for row in rows)
    summary = {
        "schema_version": "taj20-probabilistic-acceptance/v1",
        "issue": "TAJ-20 / GitHub #266",
        "acceptance": "PASS" if all(gates.values()) else "BLOCKED",
        "source_head": plan.get("source_head"),
        "models": len(model_ids),
        "games": len(games),
        "expected_pairs": EXPECTED_PAIRS,
        "observed_pairs": len(rows),
        "normalized_status_counts": dict(sorted(counts.items())),
        "gates": gates,
        "blockers": {
            "duplicate_task_keys": duplicate_keys,
            "missing_task_keys": missing_keys,
            "unexpected_task_keys": unexpected_keys,
            "invalid_status_task_keys": invalid_status,
            "unmapped_raw_status_task_keys": unmapped,
            "missing_source_evidence_task_keys": missing_source_evidence,
        },
        "scientific_boundary": {
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
    }
    _atomic_json(root / "CAMPAIGN_SUMMARY.json", summary)
    return summary


def write_integrity(root: Path) -> dict[str, str]:
    manifest_path = root / "ARTIFACT_MANIFEST.json"
    sums_path = root / "SHA256SUMS"
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path in {manifest_path, sums_path}:
            continue
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    _atomic_json(
        manifest_path,
        {"schema_version": "taj20-probabilistic-artifacts/v1", "files": files},
    )
    manifest_sha = _sha256(manifest_path)
    lines = [f"{item['sha256']}  {item['path']}" for item in files]
    lines.append(f"{manifest_sha}  ARTIFACT_MANIFEST.json")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"manifest_sha256": manifest_sha, "sha256sums_sha256": _sha256(sums_path)}


def execute_campaign(*, root: Path, campaign_id: str, seed: int) -> dict[str, Any]:
    if root.exists():
        raise Taj20MatrixError(f"refusing to reuse campaign root: {root}")
    root.mkdir(parents=True)
    plan = build_matrix_plan(campaign_id=campaign_id, root=root, seed=seed)
    _atomic_json(root / "MATRIX_PLAN.json", plan)
    normalized_rows: list[dict[str, Any]] = []
    for game in plan["games"]:
        config = _base_config(
            output=root / "ppl-runs",
            run_id=f"{campaign_id}-{game}",
            game=game,
            seed=seed,
        )
        report = run_probabilistic(config)
        run_dir = Path(str(report["run_dir"]))
        results = _read_json(run_dir / "results.json")
        if not isinstance(results, list) or len(results) != EXPECTED_PROBABILISTIC_MODELS:
            raise Taj20MatrixError(
                "per-game result count mismatch: "
                f"game={game} rows={len(results) if isinstance(results, list) else 'invalid'}"
            )
        game_rows = [_normalize_result(row, game=game, run_dir=run_dir) for row in results]
        if len({row["model_id"] for row in game_rows}) != EXPECTED_PROBABILISTIC_MODELS:
            raise Taj20MatrixError(f"per-game result identity mismatch: game={game}")
        normalized_rows.extend(game_rows)
        _write_jsonl(root / "NORMALIZED_RESULTS.jsonl", normalized_rows)
        _atomic_json(
            root / "PROGRESS.json",
            {
                "status": "RUNNING",
                "completed_games": plan["games"].index(game) + 1,
                "total_games": EXPECTED_GAMES,
                "completed_pairs": len(normalized_rows),
                "expected_pairs": EXPECTED_PAIRS,
                "holdout": "CLOSED",
                "prospective": "CLOSED",
            },
        )
    summary = verify_campaign(root)
    integrity = write_integrity(root)
    return {**summary, "integrity": integrity}


def plan_only(*, root: Path, campaign_id: str, seed: int) -> dict[str, Any]:
    if root.exists():
        raise Taj20MatrixError(f"refusing to reuse plan root: {root}")
    root.mkdir(parents=True)
    plan = build_matrix_plan(campaign_id=campaign_id, root=root, seed=seed)
    _atomic_json(root / "MATRIX_PLAN.json", plan)
    integrity = write_integrity(root)
    return {"status": "PLANNED", "root": str(root), "integrity": integrity, **plan}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-20 incremental probabilistic 76x6 runner")
    parser.add_argument("mode", choices=("plan", "run", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--seed", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    campaign_id = args.campaign_id or time.strftime("taj20-prob-%Y%m%d-%H%M%S")
    if args.mode == "plan":
        result = plan_only(root=root, campaign_id=campaign_id, seed=args.seed)
        print("TAJ20_PROB_PLAN=PASS")
        print(f"MODELS={result['models']}")
        print(f"GAMES={len(result['games'])}")
        print(f"PLANNED_PAIRS={result['expected_pairs']}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        return 0
    if args.mode == "run":
        result = execute_campaign(root=root, campaign_id=campaign_id, seed=args.seed)
        print(f"TAJ20_PROB_ACCEPTANCE={result['acceptance']}")
        print(f"OBSERVED_PAIRS={result['observed_pairs']}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print(f"ARTIFACT_MANIFEST_SHA256={result['integrity']['manifest_sha256']}")
        print(f"SHA256SUMS_SHA256={result['integrity']['sha256sums_sha256']}")
        return 0 if result["acceptance"] == "PASS" else 20
    result = verify_campaign(root)
    print(f"TAJ20_PROB_ACCEPTANCE={result['acceptance']}")
    print(f"OBSERVED_PAIRS={result['observed_pairs']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    return 0 if result["acceptance"] == "PASS" else 20


if __name__ == "__main__":
    raise SystemExit(main())
