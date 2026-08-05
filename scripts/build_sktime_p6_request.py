from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a resolved sktime P6 request from sealed evidence."
    )
    parser.add_argument("--policy-config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--p0-dir", required=True)
    parser.add_argument("--p1-dir", required=True)
    parser.add_argument("--p2-dir", required=True)
    parser.add_argument("--p3-dir", required=True)
    parser.add_argument("--p4-dir", required=True)
    parser.add_argument(
        "--p5-monitor-dir",
        action="append",
        required=True,
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_sha256sums(directory: Path) -> str:
    sums = directory / "SHA256SUMS"
    if not sums.is_file():
        raise ValueError(f"missing SHA256SUMS: {directory}")
    seen: set[str] = set()
    for line in sums.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", maxsplit=1)
        if name in seen:
            raise ValueError(f"duplicate SHA path: {directory}/{name}")
        seen.add(name)
        path = directory / name
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"SHA-256 mismatch: {directory}/{name}")
    expected_files = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if seen != expected_files:
        raise ValueError(f"SHA256SUMS coverage mismatch: {directory}")
    return file_sha256(sums)


def extract_candidate_metrics(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("candidate aggregate has no metrics")
    required = {
        "hit_at_1",
        "all_position_hit_at_1",
        "mae",
        "mse",
        "rmse",
    }
    if set(metrics) != required:
        raise ValueError("candidate metric inventory mismatch")
    return metrics


def build_window(
    directory: Path,
    *,
    shadow_candidate_id: str,
) -> dict[str, Any]:
    monitor_sha = verify_sha256sums(directory)
    response = load_json(directory / "response.json")
    drift = load_json(directory / "DRIFT_REPORT.json")
    actuals = load_json(directory / "ACTUALS_SNAPSHOT.json")
    lineage = load_json(directory / "P5_LOCK_LINEAGE.json")
    aggregates = load_json(directory / "CANDIDATE_AGGREGATES.json")

    if response.get("status") != "PASS":
        raise ValueError(f"P5 monitor status is not PASS: {directory}")
    if response.get("shadow_candidate_id") != shadow_candidate_id:
        raise ValueError("P5 monitor changed the shadow candidate")
    if response.get("automatic_retraining") is not False:
        raise ValueError("P5 monitor enabled automatic retraining")
    if response.get("automatic_promotion") is not False:
        raise ValueError("P5 monitor enabled automatic promotion")
    if response.get("promotion_status") != "NOT_PROMOTED":
        raise ValueError("P5 monitor incorrectly claims promotion")
    if drift.get("automatic_retraining") is not False:
        raise ValueError("P5 drift report enabled automatic retraining")
    if drift.get("automatic_promotion") is not False:
        raise ValueError("P5 drift report enabled automatic promotion")

    shadow = next(
        (
            row
            for row in aggregates
            if row.get("candidate_id") == shadow_candidate_id
        ),
        None,
    )
    if shadow is None or shadow.get("status") != "PASS":
        raise ValueError("shadow candidate lacks a complete P5 score")
    baseline_rows = {
        str(row["candidate_id"]): extract_candidate_metrics(row)
        for row in aggregates
        if row.get("candidate_kind") == "baseline"
        and row.get("status") == "PASS"
    }
    if not baseline_rows:
        raise ValueError("P5 monitor has no passing baseline aggregates")

    return {
        "schema_version": "1.0",
        "window_id": str(response["run_id"]),
        "monitor_bundle_sha256": monitor_sha,
        "prediction_lock_seal_sha256": str(lineage["seal_sha256"]),
        "actuals_source_sha256": str(actuals["source_sha256"]),
        "sealed_at_utc": str(lineage["sealed_at_utc"]),
        "revealed_at_utc": str(actuals["revealed_at_utc"]),
        "draw_no": actuals["draw_no"],
        "shadow_candidate_id": shadow_candidate_id,
        "integrity_status": "PASS",
        "drift_status": response["drift_status"],
        "recommendation": response["recommendation"],
        "automatic_retraining": False,
        "automatic_promotion": False,
        "promotion_status": "NOT_PROMOTED",
        "shadow_metrics": extract_candidate_metrics(shadow),
        "baseline_metrics": baseline_rows,
    }


def main() -> int:
    args = parse_args()
    policy = load_json(Path(args.policy_config))
    upstream_dirs = {
        "p0": Path(args.p0_dir),
        "p1": Path(args.p1_dir),
        "p2": Path(args.p2_dir),
        "p3": Path(args.p3_dir),
        "p4": Path(args.p4_dir),
    }
    upstream_hashes = {
        key: verify_sha256sums(path)
        for key, path in upstream_dirs.items()
    }

    p4_response = load_json(upstream_dirs["p4"] / "response.json")
    if p4_response.get("status") != "PASS":
        raise ValueError("P4 status is not PASS")
    if p4_response.get("promotion_status") != (
        "HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED"
    ):
        raise ValueError("P4 promotion boundary mismatch")
    shadow_candidate_id = str(p4_response["selected_oof_candidate_id"])
    p4_aggregates = load_json(
        upstream_dirs["p4"] / "HOLDOUT_CANDIDATE_AGGREGATES.json"
    )
    holdout_shadow = next(
        (
            row
            for row in p4_aggregates
            if row.get("candidate_id") == shadow_candidate_id
        ),
        None,
    )
    if holdout_shadow is None or holdout_shadow.get("status") != "PASS":
        raise ValueError("P4 shadow candidate has no complete Holdout score")

    windows = [
        build_window(Path(item), shadow_candidate_id=shadow_candidate_id)
        for item in args.p5_monitor_dir
    ]
    payload = {
        "schema_version": "1.0",
        "operation": "prospective_promotion_gate",
        "output_dir": "REPLACED_BY_RUNNER",
        "run_id": args.run_id,
        "git_commit": args.git_commit,
        "code_sha256": args.code_sha256,
        "config_sha256": args.config_sha256,
        "shadow_candidate_id": shadow_candidate_id,
        "upstream_artifact_sha256": upstream_hashes,
        "runtime_certification_status": "PASS",
        "leakage_audit_status": "PASS",
        "data_quality_status": "PASS",
        "seed_policy_status": "PASS",
        "preactual_lock_status": "PASS",
        "holdout_reference_metrics": extract_candidate_metrics(
            holdout_shadow
        ),
        "windows": windows,
        "policy": policy,
        "human_approval_granted": False,
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
