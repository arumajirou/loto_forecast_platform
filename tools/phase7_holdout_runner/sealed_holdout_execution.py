from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from main_preflight import (
    EXPECTED_CANONICAL_SHA256,
    EXPECTED_DEVELOPMENT_SHA256,
    EXPECTED_DERIVED_RUNNER_SHA256,
    EXPECTED_FREEZE_SHA256,
    EXPECTED_ORIGINAL_RUNNER_SHA256,
    default_repo_root,
    resolve_canonical,
    run_preflight,
    sha256_file,
)

SCIENTIFIC_GIT_COMMIT: Final = "179bcbc9a51a60f0badfe7faa25f3818ab686229"
EXPECTED_HOLDOUT_DRAWS: Final = 50
HEX64_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class HoldoutExecutionError(RuntimeError):
    """Raised when sealed Phase 7 Holdout execution cannot be proven safe."""


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HoldoutExecutionError(f"JSON root is not an object: {path}")
    return payload


def directory_snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def collect_hex64(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            found.update(collect_hex64(item))
    elif isinstance(value, list):
        for item in value:
            found.update(collect_hex64(item))
    elif isinstance(value, str):
        candidate = value.lower()
        if HEX64_RE.fullmatch(candidate):
            found.add(candidate)
    return found


def require_metric_and_baseline_evidence(artifacts: Path) -> dict[str, list[str]]:
    evidence_files = [
        path
        for path in sorted(artifacts.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".json", ".csv"}
    ]
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for path in evidence_files
    )

    required_metrics = ["hit_at_1", "mae", "mse", "rmse"]
    missing_metrics = [token for token in required_metrics if token not in text]
    if missing_metrics:
        raise HoldoutExecutionError(
            "required metric evidence missing: " + ", ".join(missing_metrics)
        )

    if not any(
        token in text
        for token in ("position_hit_at_1", "per_position_hit_at_1", "position hit@")
    ):
        raise HoldoutExecutionError("position Hit@±1 evidence missing")
    if not any(
        token in text
        for token in ("all_position_hit_at_1", "all_positions_hit_at_1", "all-position")
    ):
        raise HoldoutExecutionError("all-position Hit@±1 evidence missing")

    required_baselines = ["random", "fixed", "mean", "median", "frequency"]
    missing_baselines = [token for token in required_baselines if token not in text]
    if missing_baselines:
        raise HoldoutExecutionError(
            "required baseline evidence missing: " + ", ".join(missing_baselines)
        )
    if "last" not in text and "recent" not in text:
        raise HoldoutExecutionError("last/recent baseline evidence missing")
    if "statistical_ar1" not in text and "ar1" not in text:
        raise HoldoutExecutionError("statistical AR1 baseline evidence missing")

    return {
        "metrics": required_metrics,
        "baselines": [
            "random",
            "fixed",
            "mean",
            "median",
            "last_or_recent",
            "frequency",
            "statistical_ar1",
        ],
    }


def validate_completed_artifacts(artifacts: Path) -> dict[str, Any]:
    progress_path = artifacts / "progress.json"
    if not progress_path.is_file():
        raise HoldoutExecutionError(f"Holdout progress missing: {progress_path}")
    progress = load_json(progress_path)
    if progress.get("status") != "PASS":
        raise HoldoutExecutionError(f"Holdout status is not PASS: {progress.get('status')!r}")

    holdout_done = int(progress.get("holdout_draws_done", -1))
    actuals_accessed = int(progress.get("actuals_accessed", -1))
    if holdout_done != EXPECTED_HOLDOUT_DRAWS:
        raise HoldoutExecutionError(
            f"Holdout draw count mismatch: expected={EXPECTED_HOLDOUT_DRAWS} actual={holdout_done}"
        )
    if actuals_accessed != EXPECTED_HOLDOUT_DRAWS:
        raise HoldoutExecutionError(
            "actual access count mismatch: "
            f"expected={EXPECTED_HOLDOUT_DRAWS} actual={actuals_accessed}"
        )

    lock_root = artifacts / "prediction_locks"
    lock_files = sorted(path for path in lock_root.rglob("*") if path.is_file())
    if len(lock_files) != EXPECTED_HOLDOUT_DRAWS:
        raise HoldoutExecutionError(
            "prediction lock count mismatch: "
            f"expected={EXPECTED_HOLDOUT_DRAWS} actual={len(lock_files)}"
        )
    lock_hashes = {sha256_file(path) for path in lock_files}
    if len(lock_hashes) != EXPECTED_HOLDOUT_DRAWS:
        raise HoldoutExecutionError("prediction lock SHA-256 values are not unique")

    chain_path = artifacts / "SEQUENTIAL_LOCK_CHAIN.jsonl"
    if not chain_path.is_file():
        raise HoldoutExecutionError(f"sequential lock chain missing: {chain_path}")
    chain_records = [
        json.loads(line)
        for line in chain_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(chain_records) != EXPECTED_HOLDOUT_DRAWS:
        raise HoldoutExecutionError(
            "sequential lock chain length mismatch: "
            f"expected={EXPECTED_HOLDOUT_DRAWS} actual={len(chain_records)}"
        )
    chain_hashes: set[str] = set()
    for record in chain_records:
        chain_hashes.update(collect_hex64(record))
    missing_lock_hashes = lock_hashes - chain_hashes
    if missing_lock_hashes:
        raise HoldoutExecutionError(
            f"{len(missing_lock_hashes)} prediction lock SHA-256 values are absent from chain"
        )

    pre_score_seals = [
        path
        for path in artifacts.rglob("*")
        if path.is_file() and path.name.upper() == "PRE_SCORE_SEAL.JSON"
    ]
    if len(pre_score_seals) != 1:
        raise HoldoutExecutionError(
            f"PRE_SCORE_SEAL.json count mismatch: expected=1 actual={len(pre_score_seals)}"
        )
    load_json(pre_score_seals[0])

    evaluation = require_metric_and_baseline_evidence(artifacts)
    return {
        "holdout_draws_done": holdout_done,
        "actuals_accessed": actuals_accessed,
        "prediction_lock_count": len(lock_files),
        "sequential_chain_records": len(chain_records),
        "pre_score_seal": str(pre_score_seals[0]),
        "pre_score_seal_sha256": sha256_file(pre_score_seals[0]),
        "evaluation": evaluation,
    }


def default_output_root() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"phase7-sealed-holdout-v1-{stamp}"


def write_sha256sums(root: Path) -> None:
    checksum = root / "SHA256SUMS"
    files = sorted(path for path in root.rglob("*") if path.is_file() and path != checksum)
    checksum.write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(root)}\n" for path in files
        ),
        encoding="ascii",
    )


def run_holdout(*, repo_root: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise HoldoutExecutionError(f"output root already exists: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)

    try:
        preflight_root = output_root / "preflight"
        preflight = run_preflight(repo_root=repo_root, output_root=preflight_root)
        if preflight.get("safe_to_execute_holdout") is not True:
            raise HoldoutExecutionError("merged-main preflight did not authorize Holdout")
        if preflight.get("safe_to_read_actuals_before_prediction_lock") is not False:
            raise HoldoutExecutionError("preflight actual-access invariant is not fail-closed")

        derived_runner = preflight_root / "derived_bundle" / "phase7_holdout_canonical_v1.py"
        if sha256_file(derived_runner) != EXPECTED_DERIVED_RUNNER_SHA256:
            raise HoldoutExecutionError("derived runner identity changed after preflight")

        downloads = Path.home() / "Downloads"
        phase7_root = downloads / "automlforecast-phase7-holdout-20260818-101611"
        phase6c_root = downloads / "automlforecast-phase6c-ensemble-freeze-20260818-101021"
        phase3_root = downloads / "automlforecast-phase3-input-size-20260817-173808"
        original_runner = phase7_root / "phase7_holdout.py"
        original_progress = phase7_root / "artifacts" / "progress.json"
        freeze_path = phase6c_root / "artifacts" / "CANDIDATE_FREEZE.json"
        frozen_evidence = phase6c_root / "artifacts" / "frozen_component_evidence"
        development = phase3_root / "artifacts" / "numbers3-development-only.csv"
        canonical_pointer = downloads / "numbers3-current-canonical-path.txt"
        canonical = resolve_canonical(canonical_pointer)

        expected_inputs = {
            "original_runner": EXPECTED_ORIGINAL_RUNNER_SHA256,
            "freeze": EXPECTED_FREEZE_SHA256,
            "development": EXPECTED_DEVELOPMENT_SHA256,
            "canonical": EXPECTED_CANONICAL_SHA256,
        }
        input_paths = {
            "original_runner": original_runner,
            "freeze": freeze_path,
            "development": development,
            "canonical": canonical,
        }
        for name, path in input_paths.items():
            if not path.is_file():
                raise HoldoutExecutionError(f"required sealed input missing: {path}")
            actual = sha256_file(path)
            if actual != expected_inputs[name]:
                raise HoldoutExecutionError(
                    f"{name} identity mismatch: expected={expected_inputs[name]} actual={actual}"
                )
        if not original_progress.is_file():
            raise HoldoutExecutionError(f"original progress missing: {original_progress}")
        if not frozen_evidence.is_dir():
            raise HoldoutExecutionError(f"frozen component evidence missing: {frozen_evidence}")

        progress_before_sha = sha256_file(original_progress)
        frozen_before = directory_snapshot(frozen_evidence)

        artifacts = output_root / "artifacts"
        env = dict(os.environ)
        env.update(
            {
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        run = subprocess.run(
            [
                sys.executable,
                str(derived_runner),
                "--development",
                str(development),
                "--canonical",
                str(canonical),
                "--phase6c-root",
                str(phase6c_root),
                "--artifacts",
                str(artifacts),
                "--freeze-sha256",
                EXPECTED_FREEZE_SHA256,
                "--git-commit",
                SCIENTIFIC_GIT_COMMIT,
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        (output_root / "holdout.stdout.log").write_text(run.stdout, encoding="utf-8")
        (output_root / "holdout.stderr.log").write_text(run.stderr, encoding="utf-8")
        print(f"HOLDOUT_RUNNER_RC={run.returncode}")
        if run.returncode != 0:
            stdout_tail = "\n".join(run.stdout.splitlines()[-100:])
            stderr_tail = "\n".join(run.stderr.splitlines()[-120:])
            raise HoldoutExecutionError(
                "sealed Holdout runner failed\n=== STDOUT TAIL ===\n"
                + stdout_tail
                + "\n=== STDERR TAIL ===\n"
                + stderr_tail
            )

        completed = validate_completed_artifacts(artifacts)

        for name, path in input_paths.items():
            if sha256_file(path) != expected_inputs[name]:
                raise HoldoutExecutionError(f"sealed input changed during Holdout: {name}")
        if sha256_file(original_progress) != progress_before_sha:
            raise HoldoutExecutionError("original Phase7 progress changed during fresh Holdout")
        if directory_snapshot(frozen_evidence) != frozen_before:
            raise HoldoutExecutionError("frozen component evidence changed during Holdout")

        summary = {
            "schema_version": "phase7-sealed-holdout-execution/v1",
            "status": "PASS",
            "main_head_sha": preflight["main_head_sha"],
            "main_tree_sha": preflight["main_tree_sha"],
            "derived_runner_sha256": EXPECTED_DERIVED_RUNNER_SHA256,
            "candidate_freeze_sha256": EXPECTED_FREEZE_SHA256,
            "development_sha256": EXPECTED_DEVELOPMENT_SHA256,
            "canonical_sha256": EXPECTED_CANONICAL_SHA256,
            "scientific_git_commit": SCIENTIFIC_GIT_COMMIT,
            "holdout_draws_done": completed["holdout_draws_done"],
            "actuals_accessed": completed["actuals_accessed"],
            "prediction_lock_count": completed["prediction_lock_count"],
            "sequential_chain_records": completed["sequential_chain_records"],
            "pre_score_seal_sha256": completed["pre_score_seal_sha256"],
            "evaluation": completed["evaluation"],
            "lock_before_actual_contract": True,
            "sealed_inputs_unchanged": True,
            "original_phase7_state_unchanged": True,
            "safe_to_read_actuals_before_prediction_lock": False,
            "safe_to_reselect_model": False,
            "verified_at_utc": datetime.now(UTC).isoformat(),
        }
        (output_root / "SEALED_HOLDOUT_EXECUTION_SUMMARY.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return summary
    finally:
        write_sha256sums(output_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen Phase 7 canonical runner against the sealed 50-draw Holdout "
            "only after a fresh merged-main preflight, then validate prediction locks, "
            "the sequential lock chain, pre-score seal, metrics, and baselines."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=default_repo_root())
    parser.add_argument("--output-root", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root or default_output_root()
    summary = run_holdout(
        repo_root=args.repo_root.resolve(),
        output_root=output_root.resolve(),
    )
    print(f"HOLDOUT_ROOT={output_root}")
    print(f"HOLDOUT_DRAWS_DONE={summary['holdout_draws_done']}")
    print(f"ACTUALS_ACCESSED={summary['actuals_accessed']}")
    print(f"PREDICTION_LOCK_COUNT={summary['prediction_lock_count']}")
    print(f"SEQUENTIAL_CHAIN_RECORDS={summary['sequential_chain_records']}")
    print(f"PRE_SCORE_SEAL_SHA256={summary['pre_score_seal_sha256']}")
    print("LOCK_BEFORE_ACTUAL_CONTRACT=PASS")
    print("SEALED_INPUTS_UNCHANGED=PASS")
    print("ORIGINAL_PHASE7_STATE_UNCHANGED=PASS")
    print("SAFE_TO_READ_ACTUALS_BEFORE_PREDICTION_LOCK=NO")
    print("SAFE_TO_RESELECT_MODEL=NO")
    print("SAFE_TO_REVIEW_HOLDOUT_EVIDENCE=YES")
    print("SHA256SUMS_CREATED=YES")
    print("STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
