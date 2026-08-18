from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_BASELINES = (
    "random",
    "fixed",
    "mean",
    "median",
    "last",
    "frequency",
    "statistical_ar1",
)
EXPECTED_GAME = "numbers3"
EXPECTED_BROAD_ID = "logistic"
EXPECTED_PROBABILISTIC_ID = "pp-multinomial-dglm"
EXPECTED_SEED = 42


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_checksums(root: Path) -> int:
    checksum_path = root / "SHA256SUMS"
    if not checksum_path.is_file():
        raise FileNotFoundError(f"missing SHA256SUMS: {checksum_path}")

    root_resolved = root.resolve()
    verified = 0
    for raw_line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        expected, relative = raw_line.split("  ", 1)
        path = (root / relative).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"checksum path escapes smoke root: {relative}") from exc
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


def _lock_payload(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    seed_results = row.get("seed_results", [])
    if len(seed_results) != 1 or int(seed_results[0].get("seed", -1)) != EXPECTED_SEED:
        raise ValueError(f"unexpected seed evidence for {row.get('candidate_id')}")
    lock_info = seed_results[0].get("prediction_lock", {})
    lock_path = Path(str(lock_info.get("path", ""))).resolve()
    try:
        lock_path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"prediction lock escapes smoke root: {row.get('candidate_id')}"
        ) from exc
    if not lock_path.is_file():
        raise FileNotFoundError(f"prediction lock missing: {lock_path}")
    if _sha256(lock_path) != str(lock_info.get("sha256", "")):
        raise ValueError(f"prediction lock digest mismatch: {row.get('candidate_id')}")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if payload.get("actuals_known") is not False:
        raise ValueError(f"prediction lock exposes actuals: {row.get('candidate_id')}")
    if not payload.get("predictions"):
        raise ValueError(f"prediction lock has no predictions: {row.get('candidate_id')}")
    return payload


def verify_smoke(root: Path) -> dict[str, Any]:
    root = root.resolve()
    summary_path = root / "campaign_summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"missing campaign summary: {summary_path}")

    checksum_count = _verify_checksums(root)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "SUCCEEDED":
        raise ValueError(f"campaign status is not SUCCEEDED: {summary.get('status')}")
    if summary.get("matrix_complete") is not True:
        raise ValueError("representative smoke matrix is incomplete")
    if summary.get("games") != [EXPECTED_GAME]:
        raise ValueError(f"unexpected smoke games: {summary.get('games')}")
    if summary.get("seeds") != [EXPECTED_SEED]:
        raise ValueError(f"unexpected smoke seeds: {summary.get('seeds')}")
    if int(summary.get("catalog_models", -1)) != 2:
        raise ValueError("representative smoke must contain exactly two model identities")
    if int(summary.get("expected_model_game_pairs", -1)) != 2:
        raise ValueError("representative smoke expected pair count must be 2")
    if int(summary.get("observed_model_game_pairs", -1)) != 2:
        raise ValueError("representative smoke observed pair count must be 2")
    if summary.get("holdout_evaluated") is not False:
        raise ValueError("Holdout must remain closed during representative smoke")
    if summary.get("prospective_evaluated") is not False:
        raise ValueError("Prospective must remain closed during representative smoke")
    if summary.get("promotion") is not False:
        raise ValueError("Promotion must remain closed during representative smoke")

    results = list(summary.get("results", []))
    baseline_rows = [row for row in results if row.get("source") == "baseline"]
    catalog_rows = [row for row in results if row.get("source") == "catalog"]
    probabilistic_rows = [row for row in results if row.get("source") == "probabilistic"]

    baseline_ids = {str(row.get("candidate_id")) for row in baseline_rows}
    expected_baseline_ids = {f"baseline:{name}" for name in EXPECTED_BASELINES}
    if baseline_ids != expected_baseline_ids:
        raise ValueError(f"unexpected baseline rows: {sorted(baseline_ids)}")
    if len(catalog_rows) != 1 or catalog_rows[0].get("candidate_id") != EXPECTED_BROAD_ID:
        raise ValueError("representative Broad route is not exactly logistic")
    if (
        len(probabilistic_rows) != 1
        or probabilistic_rows[0].get("candidate_id") != EXPECTED_PROBABILISTIC_ID
    ):
        raise ValueError(
            "representative probabilistic route is not exactly pp-multinomial-dglm"
        )

    expected_rows = baseline_rows + catalog_rows + probabilistic_rows
    if len(expected_rows) != 9:
        raise ValueError(f"representative smoke must have exactly 9 result rows, got {len(expected_rows)}")
    for row in expected_rows:
        if row.get("game") != EXPECTED_GAME:
            raise ValueError(f"unexpected result game: {row.get('game')}")
        if row.get("status") != "SUCCEEDED":
            raise ValueError(
                f"representative route failed: {row.get('candidate_id')} status={row.get('status')}"
            )
        _lock_payload(root, row)

    probabilistic_seed = probabilistic_rows[0]["seed_results"][0]
    runtime_samples = probabilistic_seed.get("runtime_samples", [])
    if not runtime_samples:
        raise ValueError("probabilistic smoke row has no runtime samples")
    for sample in runtime_samples:
        metadata = sample.get("metadata", {})
        if metadata.get("route") != "probabilistic_primary_native_development_oof":
            raise ValueError("probabilistic smoke did not use the primary-native OOF route")
        if metadata.get("target_actual_present_in_fit_bundle") is not False:
            raise ValueError("probabilistic fit bundle contained the target actual")
        if metadata.get("target_actual_read") is not False:
            raise ValueError("probabilistic predictor read the target actual before sealing")

    return {
        "baseline_succeeded": len(baseline_rows),
        "broad_status": catalog_rows[0]["status"],
        "probabilistic_status": probabilistic_rows[0]["status"],
        "prediction_locks_verified": len(expected_rows),
        "checksummed_artifacts_verified": checksum_count,
        "sha256sums_sha256": _sha256(root / "SHA256SUMS"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_smoke(args.root)
    except Exception as exc:  # noqa: BLE001 - verifier must fail visibly on every contract break
        print("TAJ21_REPRESENTATIVE_SMOKE=FAIL")
        print(f"REASON={type(exc).__name__}: {exc}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 2

    print("TAJ21_REPRESENTATIVE_SMOKE=PASS")
    print(f"GAME={EXPECTED_GAME}")
    print(f"BASELINES_SUCCEEDED={result['baseline_succeeded']}/{len(EXPECTED_BASELINES)}")
    print(f"BROAD_{EXPECTED_BROAD_ID.upper()}={result['broad_status']}")
    print(
        "PROBABILISTIC_PP_MULTINOMIAL_DGLM="
        f"{result['probabilistic_status']}"
    )
    print("EXPECTED_MODEL_GAME_PAIRS=2")
    print("OBSERVED_MODEL_GAME_PAIRS=2")
    print(f"PREDICTION_LOCKS_VERIFIED={result['prediction_locks_verified']}")
    print(
        "CHECKSUMMED_ARTIFACTS_VERIFIED="
        f"{result['checksummed_artifacts_verified']}"
    )
    print(f"SHA256SUMS_SHA256={result['sha256sums_sha256']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
