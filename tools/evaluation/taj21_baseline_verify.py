from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS, REQUIRED_POINT_METRICS
from loto.game.geometry import known_games

EXPECTED_SEEDS = (42, 1729, 20260730)
EXPECTED_GAMES = tuple(known_games())
EXPECTED_BASELINE_IDS = tuple(REQUIRED_BASELINE_IDS)
EXPECTED_BASELINE_ROWS = len(EXPECTED_GAMES) * len(EXPECTED_BASELINE_IDS)
EXPECTED_PREDICTION_LOCKS = EXPECTED_BASELINE_ROWS * len(EXPECTED_SEEDS)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_checksums(root: Path) -> int:
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise FileNotFoundError(f"missing SHA256SUMS: {sums_path}")

    root_resolved = root.resolve()
    verified = 0
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = (root / relative).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"checksum path escapes baseline root: {relative}") from exc
        if not path.is_file():
            raise FileNotFoundError(f"checksummed artifact is missing: {relative}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"checksum mismatch for {relative}: expected={expected} actual={actual}"
            )
        verified += 1
    if verified == 0:
        raise ValueError("SHA256SUMS contains no artifacts")
    return verified


def _prediction_lock(root: Path, row: dict[str, Any], seed_result: dict[str, Any]) -> None:
    lock_info = seed_result.get("prediction_lock", {})
    lock_path = Path(str(lock_info.get("path", ""))).resolve()
    try:
        lock_path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"prediction lock escapes baseline root: {lock_path}") from exc
    if not lock_path.is_file():
        raise FileNotFoundError(f"prediction lock missing: {lock_path}")
    if _sha256(lock_path) != str(lock_info.get("sha256", "")):
        raise ValueError(f"prediction lock digest mismatch: {row.get('candidate_id')}")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if payload.get("actuals_known") is not False:
        raise ValueError(f"prediction lock exposes actuals: {row.get('candidate_id')}")
    if not payload.get("predictions"):
        raise ValueError(f"prediction lock has no predictions: {row.get('candidate_id')}")


def _verify_seed_evidence(root: Path, row: dict[str, Any]) -> int:
    seed_results = list(row.get("seed_results", []))
    seeds = tuple(int(item.get("seed", -1)) for item in seed_results)
    if seeds != EXPECTED_SEEDS:
        raise ValueError(f"unexpected seed inventory for {row.get('candidate_id')}: {seeds}")

    for seed_result in seed_results:
        metrics = seed_result.get("metrics", {})
        missing = [metric for metric in REQUIRED_POINT_METRICS if metric not in metrics]
        if missing:
            raise ValueError(f"seed metrics missing {missing}: {row.get('candidate_id')}")
        by_position = metrics.get("position_hit_at_1_by_position")
        if not isinstance(by_position, dict) or not by_position:
            raise ValueError(f"position Hit@±1 evidence missing: {row.get('candidate_id')}")
        _prediction_lock(root, row, seed_result)

    seed_summary = row.get("seed_summary", {})
    for metric in REQUIRED_POINT_METRICS:
        item = seed_summary.get(metric)
        if not isinstance(item, dict):
            raise ValueError(f"seed summary missing {metric}: {row.get('candidate_id')}")
        for key in ("mean", "population_variance", "worst_value", "worst_seed"):
            if key not in item:
                raise ValueError(
                    f"seed summary field {key} missing for {metric}: {row.get('candidate_id')}"
                )
    return len(seed_results)


def verify_baselines(root: Path) -> dict[str, Any]:
    root = root.resolve()
    checksum_count = _verify_checksums(root)

    input_manifest = json.loads((root / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    if input_manifest.get("synthetic") is not False:
        raise ValueError("formal baseline reference must not use synthetic data")
    if input_manifest.get("raw_files_mutated") is not False:
        raise ValueError("baseline execution must not mutate raw files")
    if tuple(input_manifest.get("games", [])) != EXPECTED_GAMES:
        raise ValueError("input manifest does not contain the exact six canonical games")
    input_rows = list(input_manifest.get("files", []))
    if len(input_rows) != len(EXPECTED_GAMES):
        raise ValueError("input manifest must contain exactly six source files")
    for item in input_rows:
        digest = str(item.get("sha256", ""))
        if len(digest) != 64:
            raise ValueError(f"invalid input SHA-256: {item}")
        if int(item.get("rows", 0)) <= 0:
            raise ValueError(f"invalid input row count: {item}")

    reference = json.loads((root / "BASELINE_REFERENCE.json").read_text(encoding="utf-8"))
    if reference.get("status") != "EXECUTED":
        raise ValueError("baseline reference was not executed")
    if reference.get("synthetic") is not False:
        raise ValueError("baseline reference reports synthetic data")
    if reference.get("accuracy_claim") is not False:
        raise ValueError("baseline reference must not claim model accuracy completion")

    summary_path = root / "campaign" / "campaign_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("games") != list(EXPECTED_GAMES):
        raise ValueError(f"unexpected campaign games: {summary.get('games')}")
    if summary.get("seeds") != list(EXPECTED_SEEDS):
        raise ValueError(f"unexpected campaign seeds: {summary.get('seeds')}")
    if summary.get("primary_metric") != "hit_at_1":
        raise ValueError("primary metric is not Hit@±1")
    if tuple(summary.get("required_baselines", [])) != EXPECTED_BASELINE_IDS:
        raise ValueError("baseline inventory does not match the canonical seven")
    if tuple(summary.get("required_metrics", [])) != tuple(REQUIRED_POINT_METRICS):
        raise ValueError("metric inventory does not match the canonical required metrics")
    if int(summary.get("catalog_models", -1)) != 0:
        raise ValueError("baseline reference must not execute model identities")
    if int(summary.get("expected_model_game_pairs", -1)) != 0:
        raise ValueError("baseline reference expected model pair count must be zero")
    if int(summary.get("observed_model_game_pairs", -1)) != 0:
        raise ValueError("baseline reference observed model pair count must be zero")
    if summary.get("holdout_evaluated") is not False:
        raise ValueError("Holdout must remain closed")
    if summary.get("prospective_evaluated") is not False:
        raise ValueError("Prospective must remain closed")
    if summary.get("promotion") is not False:
        raise ValueError("Promotion must remain closed")

    results = list(summary.get("results", []))
    if len(results) != EXPECTED_BASELINE_ROWS:
        raise ValueError(
            f"expected {EXPECTED_BASELINE_ROWS} baseline rows, got {len(results)}"
        )
    keys = {(str(row.get("game")), str(row.get("candidate_id"))) for row in results}
    expected_keys = {
        (game, f"baseline:{baseline}")
        for game in EXPECTED_GAMES
        for baseline in EXPECTED_BASELINE_IDS
    }
    if keys != expected_keys:
        raise ValueError("baseline game matrix contains missing or duplicate routes")

    lock_count = 0
    for row in results:
        if row.get("source") != "baseline":
            raise ValueError(f"non-baseline result found: {row.get('candidate_id')}")
        if row.get("status") != "SUCCEEDED":
            raise ValueError(
                f"baseline route failed: {row.get('game')}/{row.get('candidate_id')} "
                f"status={row.get('status')}"
            )
        lock_count += _verify_seed_evidence(root, row)
    if lock_count != EXPECTED_PREDICTION_LOCKS:
        raise ValueError(
            f"expected {EXPECTED_PREDICTION_LOCKS} prediction locks, got {lock_count}"
        )

    return {
        "baseline_rows": len(results),
        "prediction_locks": lock_count,
        "checksummed_artifacts": checksum_count,
        "sha256sums_sha256": _sha256(root / "SHA256SUMS"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_baselines(args.root)
    except Exception as exc:  # noqa: BLE001 - verifier must fail visibly
        print("TAJ21_BASELINE_REFERENCE=FAIL")
        print(f"REASON={type(exc).__name__}: {exc}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 2

    print("TAJ21_BASELINE_REFERENCE=PASS")
    print(f"GAMES={len(EXPECTED_GAMES)}")
    print(f"BASELINES={len(EXPECTED_BASELINE_IDS)}")
    print(f"BASELINE_GAME_ROWS={result['baseline_rows']}/{EXPECTED_BASELINE_ROWS}")
    print(f"SEEDS={','.join(str(seed) for seed in EXPECTED_SEEDS)}")
    print(f"PREDICTION_LOCKS_VERIFIED={result['prediction_locks']}/{EXPECTED_PREDICTION_LOCKS}")
    print(f"CHECKSUMMED_ARTIFACTS_VERIFIED={result['checksummed_artifacts']}")
    print(f"SHA256SUMS_SHA256={result['sha256sums_sha256']}")
    print("PRIMARY_METRIC=hit_at_1")
    print("SYNTHETIC=FALSE")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
