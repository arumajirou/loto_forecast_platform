from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from loto.evaluation.taj21_snapshot import (
    BASELINE_REFERENCE_GIT_COMMIT,
    BASELINE_REFERENCE_SHA256SUMS,
    validate_snapshot_item,
)

EXPECTED_GAMES = ("bingo5", "loto6", "loto7", "mini", "numbers3", "numbers4")
EXPECTED_SEEDS = (42, 1729, 20260730)
EXPECTED_MODELS = 250
EXPECTED_PAIRS = 1500
EXPECTED_BASELINES = 42
EXPECTED_FOLDS = 5
ALLOWED_STATUSES = {
    "SUCCEEDED",
    "PARTIAL_SEEDS",
    "FAILED",
    "UNAVAILABLE",
    "NOT_ROUTABLE",
    "UNSUPPORTED_GAME",
    "NON_STANDALONE_METHOD",
    "BASELINE_CONTROL",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"missing artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_checksums(root: Path) -> int:
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        raise FileNotFoundError("SHA256SUMS missing")
    verified = 0
    root_resolved = root.resolve()
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = (root / relative).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"checksum path escapes root: {relative}") from exc
        if not path.is_file():
            raise FileNotFoundError(f"checksummed artifact missing: {relative}")
        if _sha256(path) != expected:
            raise ValueError(f"checksum mismatch: {relative}")
        verified += 1
    if verified == 0:
        raise ValueError("SHA256SUMS is empty")
    return verified


def _verify_manifest(root: Path) -> int:
    manifest = _json(root / "ARTIFACT_MANIFEST.json")
    entries = list(manifest.get("entries", []))
    expected_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    }
    observed = {str(item["path"]) for item in entries}
    if observed != expected_paths:
        raise ValueError("artifact manifest inventory mismatch")
    for item in entries:
        path = root / str(item["path"])
        if _sha256(path) != str(item["sha256"]):
            raise ValueError(f"manifest digest mismatch: {item['path']}")
        if path.stat().st_size != int(item["bytes"]):
            raise ValueError(f"manifest size mismatch: {item['path']}")
    return len(entries)


def _verify_input_manifest(root: Path) -> None:
    manifest = _json(root / "INPUT_MANIFEST.json")
    if manifest.get("synthetic") is not False:
        raise ValueError("formal full campaign must use real inputs")
    if manifest.get("raw_files_mutated") is not False:
        raise ValueError("formal full campaign reports raw mutation")
    if manifest.get("frozen_snapshot_match") is not True:
        raise ValueError("formal full campaign is not bound to frozen baseline snapshot")
    if manifest.get("baseline_reference_git_commit") != BASELINE_REFERENCE_GIT_COMMIT:
        raise ValueError("baseline reference Git identity mismatch")
    if manifest.get("baseline_reference_sha256sums") != BASELINE_REFERENCE_SHA256SUMS:
        raise ValueError("baseline reference SHA256SUMS identity mismatch")
    if tuple(manifest.get("games", [])) != EXPECTED_GAMES:
        raise ValueError("input manifest does not contain exact six games")
    files = list(manifest.get("files", []))
    if len(files) != 6:
        raise ValueError("input manifest must contain six files")
    for item in files:
        if item.get("parser") != "loto.data.parser.parse_file":
            raise ValueError(f"unexpected parser identity: {item}")
        validate_snapshot_item(
            str(item.get("game", "")),
            rows=int(item.get("rows", 0)),
            sha256=str(item.get("sha256", "")),
            encoding=str(item.get("encoding", "")),
            separator=str(item.get("separator", "")),
        )


def _verify_prediction_lock(root: Path, seed_result: dict[str, Any]) -> None:
    info = seed_result.get("prediction_lock", {})
    path = Path(str(info.get("path", ""))).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"prediction lock escapes full-run root: {path}") from exc
    if not path.is_file() or _sha256(path) != str(info.get("sha256", "")):
        raise ValueError(f"prediction lock missing or digest mismatch: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("actuals_known") is not False or not payload.get("predictions"):
        raise ValueError(f"invalid prediction lock payload: {path}")


def _verify_success_row(root: Path, row: dict[str, Any]) -> int:
    seed_results = list(row.get("seed_results", []))
    seeds = tuple(int(item.get("seed", -1)) for item in seed_results)
    if seeds != EXPECTED_SEEDS:
        raise ValueError(f"unexpected seed inventory: {row['game']}/{row['candidate_id']}")
    position_summary = row.get("seed_summary", {}).get("position_hit_at_1_by_position", {})
    if not position_summary:
        raise ValueError(f"per-position seed summary missing: {row['candidate_id']}")
    for item in position_summary.values():
        if int(item.get("count", 0)) != len(EXPECTED_SEEDS):
            raise ValueError(f"per-position seed summary incomplete: {row['candidate_id']}")
    for seed_result in seed_results:
        folds = list(seed_result.get("fold_metrics", []))
        if len(folds) != EXPECTED_FOLDS:
            raise ValueError(f"fold metric inventory incomplete: {row['candidate_id']}")
        if len({int(item["fold_id"]) for item in folds}) != EXPECTED_FOLDS:
            raise ValueError(f"duplicate fold metrics: {row['candidate_id']}")
        evidence = seed_result.get("actual_read_evidence", {})
        source = evidence.get("scoring_source_contract", {})
        if evidence.get("verification_actual_read_after_prediction_seal") is not True:
            raise ValueError(f"post-seal actual-read evidence missing: {row['candidate_id']}")
        if source.get("prediction_lock_before_target_actual") is not True:
            raise ValueError(f"source ordering contract missing: {row['candidate_id']}")
        _verify_prediction_lock(root, seed_result)
    return len(seed_results)


def verify_full(root: Path, *, expected_git_commit: str | None = None) -> dict[str, int]:
    root = root.resolve()
    checksum_count = _verify_checksums(root)
    manifest_count = _verify_manifest(root)
    _verify_input_manifest(root)
    summary = _json(root / "campaign_summary.json")
    report = _json(root / "VERIFICATION_REPORT.json")
    paired = _json(root / "PAIRED_COMPARISONS.json")
    artifact_manifest = _json(root / "ARTIFACT_MANIFEST.json")

    if expected_git_commit is not None:
        if summary.get("git_commit") != expected_git_commit:
            raise ValueError("campaign Git commit does not match expected commit")
        if report.get("git_commit") != expected_git_commit:
            raise ValueError("verification report Git commit does not match expected commit")
        if artifact_manifest.get("git_commit") != expected_git_commit:
            raise ValueError("artifact manifest Git commit does not match expected commit")
    if int(summary.get("catalog_models", -1)) != EXPECTED_MODELS:
        raise ValueError("formal catalog is not Unified250")
    if int(summary.get("expected_model_game_pairs", -1)) != EXPECTED_PAIRS:
        raise ValueError("expected model-game matrix is not 1500")
    if int(summary.get("observed_model_game_pairs", -1)) != EXPECTED_PAIRS:
        raise ValueError("observed model-game matrix is not 1500")
    if summary.get("matrix_complete") is not True:
        raise ValueError("formal model-game matrix is incomplete")
    if tuple(summary.get("games", [])) != EXPECTED_GAMES:
        raise ValueError("campaign games are not exact canonical six")
    if tuple(summary.get("seeds", [])) != EXPECTED_SEEDS:
        raise ValueError("campaign seeds are not approved inventory")
    if summary.get("primary_metric") != "hit_at_1":
        raise ValueError("primary metric is not Hit@±1")
    if summary.get("holdout_evaluated") is not False:
        raise ValueError("Holdout must remain closed")
    if summary.get("prospective_evaluated") is not False or summary.get("promotion") is not False:
        raise ValueError("Prospective and Promotion must remain closed")

    results = list(summary.get("results", []))
    candidates = [row for row in results if row.get("source") in {"catalog", "probabilistic"}]
    baselines = [row for row in results if row.get("source") == "baseline"]
    if len(candidates) != EXPECTED_PAIRS:
        raise ValueError("candidate result inventory is not 1500")
    if len({(row["game"], row["candidate_id"]) for row in candidates}) != EXPECTED_PAIRS:
        raise ValueError("candidate matrix contains duplicate pairs")
    if len(baselines) != EXPECTED_BASELINES or any(
        row.get("status") != "SUCCEEDED" for row in baselines
    ):
        raise ValueError("seven-baseline six-game matrix is not fully successful")
    if any(row.get("status") not in ALLOWED_STATUSES for row in candidates):
        raise ValueError("candidate matrix contains unknown status")

    successful_seed_results = 0
    for row in results:
        if row.get("status") == "SUCCEEDED":
            successful_seed_results += _verify_success_row(root, row)

    comparisons = list(paired.get("comparisons", []))
    if len(comparisons) != EXPECTED_PAIRS:
        raise ValueError("paired comparison inventory is not 1500")
    if len({(row["game"], row["candidate_id"]) for row in comparisons}) != EXPECTED_PAIRS:
        raise ValueError("paired comparison matrix contains duplicate pairs")
    succeeded_candidates = {
        (row["game"], row["candidate_id"])
        for row in candidates
        if row["status"] == "SUCCEEDED"
    }
    valid_comparisons = {
        (row["game"], row["candidate_id"])
        for row in comparisons
        if row["comparison_status"] == "VALID"
    }
    if valid_comparisons != succeeded_candidates:
        raise ValueError("valid paired comparisons do not match successful candidates")
    for item in comparisons:
        if item["comparison_status"] == "VALID":
            value = float(item["holm_adjusted_p_value"])
            if not 0.0 <= value <= 1.0:
                raise ValueError("Holm adjusted p-value outside [0,1]")

    if report.get("status") != "PASS":
        raise ValueError("verification report is not PASS")
    if report.get("fold_evidence_complete") is not True:
        raise ValueError("verification report fold gate failed")
    if report.get("all_seed_per_position_summary_complete") is not True:
        raise ValueError("verification report per-position gate failed")
    if report.get("post_seal_actual_read_evidence_complete") is not True:
        raise ValueError("verification report ordering gate failed")
    return {
        "candidate_rows": len(candidates),
        "baseline_rows": len(baselines),
        "successful_seed_results": successful_seed_results,
        "paired_rows": len(comparisons),
        "valid_paired_rows": len(valid_comparisons),
        "manifest_entries": manifest_count,
        "checksummed_artifacts": checksum_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--git-commit", default=None)
    args = parser.parse_args()
    try:
        result = verify_full(args.root, expected_git_commit=args.git_commit)
    except Exception as exc:  # noqa: BLE001 - independent verifier must fail visibly
        print("TAJ21_FULL_OOF_VERIFY=BLOCKED")
        print(f"REASON={type(exc).__name__}: {exc}")
        return 2
    print("TAJ21_FULL_OOF_VERIFY=PASS")
    print(f"CANDIDATE_ROWS={result['candidate_rows']}/1500")
    print(f"BASELINE_ROWS={result['baseline_rows']}/42")
    print(f"PAIRED_ROWS={result['paired_rows']}/1500")
    print(f"VALID_PAIRED_ROWS={result['valid_paired_rows']}")
    print(f"SUCCESSFUL_SEED_RESULTS={result['successful_seed_results']}")
    print(f"ARTIFACT_MANIFEST_ENTRIES={result['manifest_entries']}")
    print(f"CHECKSUMMED_ARTIFACTS={result['checksummed_artifacts']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
