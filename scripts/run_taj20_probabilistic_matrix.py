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
    """Raised when the frozen TAJ-20 probabilistic matrix cannot be executed."""


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


def _verify_sha256s(root: Path) -> tuple[bool, list[str]]:
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        return False, ["SHA256SUMS missing"]
    failures: list[str] = []
    for number, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"invalid SHA256SUMS line {number}")
            continue
        target = (root / relative).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            failures.append(f"path escapes root: {relative}")
            continue
        if not target.is_file():
            failures.append(f"missing: {relative}")
        elif _sha256(target) != expected:
            failures.append(f"sha mismatch: {relative}")
    return not failures, failures


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


def read_frozen_plan(preflight_root: Path) -> dict[str, Any]:
    summary = _read_json(preflight_root / "PRECHECK_SUMMARY.json")
    plan = _read_json(preflight_root / "INCREMENTAL_MATRIX_PLAN.json")
    sha_ok, sha_failures = _verify_sha256s(preflight_root)
    if not sha_ok:
        raise Taj20MatrixError(f"preflight SHA256 verification failed: {sha_failures[:10]}")
    if summary.get("status") != "PASS":
        raise Taj20MatrixError(f"preflight is not PASS: {summary.get('status')!r}")
    contract = summary.get("identity_contract") or {}
    expected_contract = {
        "probabilistic": EXPECTED_PROBABILISTIC_MODELS,
        "games": EXPECTED_GAMES,
        "incremental_pairs": EXPECTED_PAIRS,
        "final_pairs": 1500,
        "reused_pairs": 1044,
    }
    for key, expected in expected_contract.items():
        if int(contract.get(key, -1)) != expected:
            raise Taj20MatrixError(
                f"preflight contract drift for {key}: {contract.get(key)!r} != {expected}"
            )
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or any(not isinstance(row, dict) for row in tasks):
        raise Taj20MatrixError("INCREMENTAL_MATRIX_PLAN.tasks must be a list of objects")
    keys = [str(row.get("task_key", "")) for row in tasks]
    model_ids = {str(row.get("model_id", "")) for row in tasks}
    games = {str(row.get("game", "")) for row in tasks}
    if (
        len(tasks) != EXPECTED_PAIRS
        or len(set(keys)) != EXPECTED_PAIRS
        or len(model_ids) != EXPECTED_PROBABILISTIC_MODELS
        or len(games) != EXPECTED_GAMES
        or "" in keys
        or "" in model_ids
        or "" in games
    ):
        raise Taj20MatrixError(
            "frozen incremental matrix is not exactly 76 x 6: "
            f"rows={len(tasks)} unique={len(set(keys))} "
            f"models={len(model_ids)} games={len(games)}"
        )
    if any(str(row.get("status")) != "PLANNED" for row in tasks):
        raise Taj20MatrixError("frozen incremental matrix contains non-PLANNED task")
    return {
        "summary": summary,
        "tasks": tasks,
        "model_ids": sorted(model_ids),
        "games": sorted(games),
        "sha256sums_sha256": _sha256(preflight_root / "SHA256SUMS"),
    }


def _base_config(*, output: Path, run_id: str, game: str, seed: int) -> Any:
    from loto.probabilistic.config import load_run_config

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


def _runtime_plan(config: Any) -> list[Any]:
    from loto.probabilistic.planner import build_plan

    return build_plan(config)


def validate_runtime_plan(
    *,
    game: str,
    trials: list[Any],
    frozen_tasks: list[dict[str, Any]],
) -> None:
    frozen = {
        str(row["model_id"]): row for row in frozen_tasks if str(row.get("game")) == game
    }
    if len(frozen) != EXPECTED_PROBABILISTIC_MODELS or len(trials) != EXPECTED_PROBABILISTIC_MODELS:
        raise Taj20MatrixError(f"per-game plan count mismatch: game={game}")
    trial_by_model = {str(trial.model_id): trial for trial in trials}
    if set(trial_by_model) != set(frozen):
        raise Taj20MatrixError(f"per-game frozen/runtime model identities differ: game={game}")
    for model_id, trial in trial_by_model.items():
        row = frozen[model_id]
        if trial.allowed:
            if str(trial.backend) != str(row.get("primary_backend")):
                raise Taj20MatrixError(
                    f"backend drift for {model_id}::{game}: "
                    f"runtime={trial.backend} frozen={row.get('primary_backend')}"
                )
            runtime_profile = trial.inference_profile_id
            frozen_profile = row.get("primary_profile")
            if runtime_profile != frozen_profile:
                raise Taj20MatrixError(
                    f"profile drift for {model_id}::{game}: "
                    f"runtime={runtime_profile!r} frozen={frozen_profile!r}"
                )


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
        "schema_version": "taj20-probabilistic-acceptance/v2",
        "issue": "TAJ-20 / GitHub #266",
        "acceptance": "PASS" if all(gates.values()) else "BLOCKED",
        "source_head": plan.get("source_head"),
        "preflight_sha256sums_sha256": plan.get("preflight_sha256sums_sha256"),
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
        {"schema_version": "taj20-probabilistic-artifacts/v2", "files": files},
    )
    manifest_sha = _sha256(manifest_path)
    lines = [f"{item['sha256']}  {item['path']}" for item in files]
    lines.append(f"{manifest_sha}  ARTIFACT_MANIFEST.json")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"manifest_sha256": manifest_sha, "sha256sums_sha256": _sha256(sums_path)}


def execute_campaign(
    *,
    root: Path,
    preflight_root: Path,
    campaign_id: str,
    seed: int,
) -> dict[str, Any]:
    from loto.probabilistic.runner import run_probabilistic

    if root.exists():
        raise Taj20MatrixError(f"refusing to reuse campaign root: {root}")
    frozen = read_frozen_plan(preflight_root)
    root.mkdir(parents=True)
    matrix_plan = {
        "schema_version": "taj20-probabilistic-runtime-matrix/v2",
        "issue": "TAJ-20 / GitHub #266",
        "source_head": _git_head(),
        "campaign_id": campaign_id,
        "seed": seed,
        "backend_policy": "primary_native",
        "runtime_profile": "configs/probabilistic/native_smoke.yaml",
        "preflight_root": str(preflight_root),
        "preflight_sha256sums_sha256": frozen["sha256sums_sha256"],
        "tasks": frozen["tasks"],
        "scientific_boundary": {
            "runtime_only": True,
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
    }
    _atomic_json(root / "MATRIX_PLAN.json", matrix_plan)
    normalized_rows: list[dict[str, Any]] = []
    for game in frozen["games"]:
        config = _base_config(
            output=root / "ppl-runs",
            run_id=f"{campaign_id}-{game}",
            game=game,
            seed=seed,
        )
        trials = _runtime_plan(config)
        validate_runtime_plan(game=game, trials=trials, frozen_tasks=frozen["tasks"])
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
                "completed_games": frozen["games"].index(game) + 1,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-20 frozen probabilistic 76x6 runtime runner")
    parser.add_argument("mode", choices=("run", "verify", "verify-plan"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--preflight-root", type=Path, required=True)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--seed", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    preflight_root = args.preflight_root.resolve()
    if args.mode == "verify-plan":
        frozen = read_frozen_plan(preflight_root)
        print("TAJ20_FROZEN_PLAN=PASS")
        print(f"MODELS={len(frozen['model_ids'])}")
        print(f"GAMES={len(frozen['games'])}")
        print(f"PLANNED_PAIRS={len(frozen['tasks'])}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        return 0
    if args.root is None:
        raise SystemExit("--root is required for run/verify")
    root = args.root.resolve()
    campaign_id = args.campaign_id or time.strftime("taj20-prob-%Y%m%d-%H%M%S")
    if args.mode == "run":
        result = execute_campaign(
            root=root,
            preflight_root=preflight_root,
            campaign_id=campaign_id,
            seed=args.seed,
        )
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
