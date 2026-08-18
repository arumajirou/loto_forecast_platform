from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from pr355_live_mapping_bootstrap import fetch_pr_head, git_show_bytes, repo_root

PR_FILES: Final = (
    "src/loto/evaluation/semantic_config.py",
    "tools/phase7_holdout_runner/derive_canonical_runner.py",
)
EXPECTED_PR_BLOBS: Final = {
    "src/loto/evaluation/semantic_config.py": "257d4d4a88e56f6070200a67fd86b2beca73a3c1",
    "tools/phase7_holdout_runner/derive_canonical_runner.py": "efa988d671cb31820d4a4292498dd034c85ce481",
}
EXPECTED_DERIVED_RUNNER_SHA256: Final = (
    "8077ccf023f9100344206f588dadae655eb828f3529c4d4d83ebf89c9c1ee074"
)
EXPECTED_ORIGINAL_RUNNER_SHA256: Final = (
    "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
)
EXPECTED_FREEZE_SHA256: Final = (
    "deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c"
)
EXPECTED_DEVELOPMENT_SHA256: Final = (
    "f6e0292347cd03acea95b5c788eaa51436a8b9e7e42d2fc000e9b9d366e2557e"
)
EXPECTED_CANONICAL_SHA256: Final = (
    "88fd7bf24d2864fce74e95bf6475ff4b0292446f1354d403105970d095d6592f"
)
SCIENTIFIC_GIT_COMMIT: Final = "179bcbc9a51a60f0badfe7faa25f3818ab686229"
EXPECTED_SEEDS: Final = (1, 42, 1729, 20260730)


class ReplayBootstrapError(RuntimeError):
    """Raised when replay-only verification cannot be proven safe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git identity


def directory_snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReplayBootstrapError(f"JSON root is not an object: {path}")
    return payload


def resolve_canonical(pointer: Path) -> Path:
    for line in pointer.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value:
            return Path(value)
    raise ReplayBootstrapError(f"canonical pointer is empty: {pointer}")


def default_output_root() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"phase7-canonical-replay-only-v4-{stamp}"


def materialize_pr_files(repo: Path, head: str, root: Path) -> None:
    for relative in PR_FILES:
        data = git_show_bytes(repo, head, relative)
        actual_blob = git_blob_sha1(data)
        expected_blob = EXPECTED_PR_BLOBS[relative]
        if actual_blob != expected_blob:
            raise ReplayBootstrapError(
                f"PR #355 critical blob drift: {relative} "
                f"expected={expected_blob} actual={actual_blob}"
            )
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        if git_blob_sha1(destination.read_bytes()) != expected_blob:
            raise ReplayBootstrapError(f"materialized blob mismatch: {relative}")
        print(f"PR355_CRITICAL_BLOB=PASS path={relative} blob={actual_blob}")


def verify_zero_original_progress(progress_path: Path, *, expected_sha: str) -> None:
    progress = load_json(progress_path)
    if int(progress.get("holdout_draws_done", 0)) != 0:
        raise ReplayBootstrapError("original Phase7 Holdout draws are nonzero")
    if int(progress.get("actuals_accessed", 0)) != 0:
        raise ReplayBootstrapError("original Phase7 actual access is nonzero")
    if sha256_file(progress_path) != expected_sha:
        raise ReplayBootstrapError("original Phase7 progress changed")


def validate_replay_artifacts(artifacts: Path) -> dict[str, Any]:
    replay_only = load_json(artifacts / "REPLAY_ONLY_VERIFICATION.json")
    replay_gate = load_json(artifacts / "REPLAY_GATE.json")
    progress = load_json(artifacts / "progress.json")

    if replay_only.get("status") != "PASS":
        raise ReplayBootstrapError("REPLAY_ONLY_VERIFICATION status != PASS")
    if int(replay_only.get("components_verified", -1)) != 4:
        raise ReplayBootstrapError("replay-only component count != 4")
    if int(replay_only.get("verification_trial_count", -1)) != 80:
        raise ReplayBootstrapError("replay-only trial count != 80")
    if replay_only.get("canonical_semantic_schema") != "loto.semantic-config/v1":
        raise ReplayBootstrapError("replay-only canonical schema mismatch")
    if int(replay_only.get("holdout_draws_accessed", -1)) != 0:
        raise ReplayBootstrapError("replay-only Holdout access is nonzero")
    if int(replay_only.get("actuals_accessed", -1)) != 0:
        raise ReplayBootstrapError("replay-only actual access is nonzero")
    if replay_only.get("holdout_executed") is not False:
        raise ReplayBootstrapError("replay-only reports Holdout execution")

    if progress.get("status") != "PASS":
        raise ReplayBootstrapError("progress status != PASS")
    if progress.get("phase") != "REPLAY_VERIFIED_CANONICAL_V1":
        raise ReplayBootstrapError(f"unexpected progress phase: {progress.get('phase')!r}")
    if int(progress.get("replay_components_done", -1)) != 4:
        raise ReplayBootstrapError("progress replay component count != 4")
    if int(progress.get("holdout_draws_done", -1)) != 0:
        raise ReplayBootstrapError("progress Holdout draws are nonzero")
    if int(progress.get("actuals_accessed", -1)) != 0:
        raise ReplayBootstrapError("progress actual access is nonzero")

    if replay_gate.get("status") != "PASS":
        raise ReplayBootstrapError("REPLAY_GATE status != PASS")
    if int(replay_gate.get("components_verified", -1)) != 4:
        raise ReplayBootstrapError("REPLAY_GATE component count != 4")
    if int(replay_gate.get("verification_trial_count", -1)) != 80:
        raise ReplayBootstrapError("REPLAY_GATE trial count != 80")
    if replay_gate.get("new_model_selection") is not False:
        raise ReplayBootstrapError("REPLAY_GATE reports new model selection")

    replay_dir = artifacts / "replay_verification"
    canonical_hashes: dict[str, str] = {}
    for seed in EXPECTED_SEEDS:
        evidence_path = replay_dir / f"AutoCatboost__seed{seed}__REPLAY_VERIFICATION.json"
        trials_path = replay_dir / f"AutoCatboost__seed{seed}__replay_trials.csv"
        evidence = load_json(evidence_path)
        if evidence.get("status") != "PASS":
            raise ReplayBootstrapError(f"seed={seed} replay evidence status != PASS")
        if int(evidence.get("seed", -1)) != seed:
            raise ReplayBootstrapError(f"seed={seed} evidence seed mismatch")
        if int(evidence.get("trial_count", -1)) != 20:
            raise ReplayBootstrapError(f"seed={seed} trial_count != 20")
        if evidence.get("trial_sequence_verified") is not True:
            raise ReplayBootstrapError(f"seed={seed} trial sequence verification failed")
        if evidence.get("config_verified") is not True:
            raise ReplayBootstrapError(f"seed={seed} config verification failed")
        if evidence.get("canonical_semantic_schema") != "loto.semantic-config/v1":
            raise ReplayBootstrapError(f"seed={seed} canonical schema mismatch")
        frozen_hash = str(evidence.get("canonical_semantic_sha256_frozen", ""))
        replay_hash = str(evidence.get("canonical_semantic_sha256_replay", ""))
        if len(frozen_hash) != 64 or frozen_hash != replay_hash:
            raise ReplayBootstrapError(f"seed={seed} canonical frozen/replay mismatch")
        if evidence.get("canonical_semantic_match") is not True:
            raise ReplayBootstrapError(f"seed={seed} canonical_semantic_match != true")
        if evidence.get("mlforecast_version") != "1.1.0":
            raise ReplayBootstrapError(f"seed={seed} MLForecast version mismatch")
        with trials_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 20:
            raise ReplayBootstrapError(f"seed={seed} replay trial CSV rows != 20")
        canonical_hashes[str(seed)] = frozen_hash
        print(f"SEED={seed} TRIALS=20 CANONICAL_MATCH=PASS SHA={frozen_hash}")

    lock_dir = artifacts / "prediction_locks"
    if lock_dir.exists() and any(path.is_file() for path in lock_dir.rglob("*")):
        raise ReplayBootstrapError("prediction lock files exist during replay-only verification")
    if (artifacts / "SEQUENTIAL_LOCK_CHAIN.jsonl").exists():
        raise ReplayBootstrapError("sequential lock chain exists during replay-only verification")

    return {
        "canonical_hashes": canonical_hashes,
        "components": 4,
        "trials": 80,
    }


def run_replay(*, repo: Path, output_root: Path) -> int:
    if output_root.exists():
        raise ReplayBootstrapError(f"output root already exists: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)

    pr_root = output_root / "pr355"
    pr_root.mkdir()
    head = fetch_pr_head(repo)
    print(f"PR355_FETCHED_HEAD={head}")
    print("PRIMARY_WORKTREE_SWITCHED=NO")
    print("PRIMARY_WORKTREE_RESET=NO")
    print("PRIMARY_WORKTREE_CLEAN=NO")
    print("PRIMARY_WORKTREE_STASH=NO")
    print("WINDOWS_INVALID_PATH_CHECKOUT_AVOIDED=YES")
    materialize_pr_files(repo, head, pr_root)

    downloads = Path.home() / "Downloads"
    original_phase7 = downloads / "automlforecast-phase7-holdout-20260818-101611"
    original_runner = original_phase7 / "phase7_holdout.py"
    original_progress = original_phase7 / "artifacts" / "progress.json"
    phase6c_root = downloads / "automlforecast-phase6c-ensemble-freeze-20260818-101021"
    freeze_path = phase6c_root / "artifacts" / "CANDIDATE_FREEZE.json"
    frozen_evidence = phase6c_root / "artifacts" / "frozen_component_evidence"
    development = (
        downloads
        / "automlforecast-phase3-input-size-20260817-173808"
        / "artifacts"
        / "numbers3-development-only.csv"
    )
    canonical_pointer = downloads / "numbers3-current-canonical-path.txt"

    required = (original_runner, original_progress, freeze_path, development, canonical_pointer)
    for path in required:
        if not path.is_file():
            raise ReplayBootstrapError(f"required input missing: {path}")
    if not frozen_evidence.is_dir():
        raise ReplayBootstrapError(f"frozen component evidence missing: {frozen_evidence}")

    canonical = resolve_canonical(canonical_pointer)
    if not canonical.is_file():
        raise ReplayBootstrapError(f"canonical file missing: {canonical}")

    identities = {
        "original_runner": sha256_file(original_runner),
        "original_progress": sha256_file(original_progress),
        "freeze": sha256_file(freeze_path),
        "development": sha256_file(development),
        "canonical": sha256_file(canonical),
    }
    expected = {
        "original_runner": EXPECTED_ORIGINAL_RUNNER_SHA256,
        "freeze": EXPECTED_FREEZE_SHA256,
        "development": EXPECTED_DEVELOPMENT_SHA256,
        "canonical": EXPECTED_CANONICAL_SHA256,
    }
    for name, expected_sha in expected.items():
        if identities[name] != expected_sha:
            raise ReplayBootstrapError(
                f"{name} SHA mismatch expected={expected_sha} actual={identities[name]}"
            )
    verify_zero_original_progress(original_progress, expected_sha=identities["original_progress"])
    frozen_snapshot_before = directory_snapshot(frozen_evidence)

    mlforecast_version = importlib.metadata.version("mlforecast")
    if mlforecast_version != "1.1.0":
        raise ReplayBootstrapError(f"MLForecast version drift: {mlforecast_version}")
    print("MLFORECAST_VERSION=1.1.0")

    deriver = pr_root / "tools" / "phase7_holdout_runner" / "derive_canonical_runner.py"
    semantic = pr_root / "src" / "loto" / "evaluation" / "semantic_config.py"
    bundle = output_root / "derived_bundle"
    derive = subprocess.run(
        [
            sys.executable,
            str(deriver),
            "--runner",
            str(original_runner),
            "--semantic-config-source",
            str(semantic),
            "--output-dir",
            str(bundle),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    (output_root / "derive.stdout.log").write_text(derive.stdout, encoding="utf-8")
    (output_root / "derive.stderr.log").write_text(derive.stderr, encoding="utf-8")
    if derive.returncode != 0:
        raise ReplayBootstrapError(
            "derivation failed rc=" + str(derive.returncode) + "\n" + derive.stderr[-6000:]
        )

    derived_runner = bundle / "phase7_holdout_canonical_v1.py"
    manifest = load_json(bundle / "DERIVED_RUNNER_MANIFEST.json")
    derived_sha = sha256_file(derived_runner)
    if derived_sha != EXPECTED_DERIVED_RUNNER_SHA256:
        raise ReplayBootstrapError(
            f"derived runner SHA mismatch expected={EXPECTED_DERIVED_RUNNER_SHA256} actual={derived_sha}"
        )
    if manifest.get("semantic_module_git_blob") != EXPECTED_PR_BLOBS[PR_FILES[0]]:
        raise ReplayBootstrapError("derived manifest semantic blob mismatch")
    if manifest.get("derived_runner_sha256") != derived_sha:
        raise ReplayBootstrapError("derived manifest runner SHA mismatch")
    print(f"DERIVED_RUNNER_SHA256={derived_sha}")

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
    replay = subprocess.run(
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
            "--stop-after-replay",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    (output_root / "replay.stdout.log").write_text(replay.stdout, encoding="utf-8")
    (output_root / "replay.stderr.log").write_text(replay.stderr, encoding="utf-8")
    print(f"REPLAY_RC={replay.returncode}")
    if replay.returncode != 0:
        stdout_tail = "\n".join(replay.stdout.splitlines()[-100:])
        stderr_tail = "\n".join(replay.stderr.splitlines()[-120:])
        raise ReplayBootstrapError(
            "replay-only execution failed\n=== STDOUT TAIL ===\n"
            + stdout_tail
            + "\n=== STDERR TAIL ===\n"
            + stderr_tail
        )

    evidence = validate_replay_artifacts(artifacts)

    if sha256_file(original_runner) != identities["original_runner"]:
        raise ReplayBootstrapError("original runner changed")
    if sha256_file(freeze_path) != identities["freeze"]:
        raise ReplayBootstrapError("Candidate Freeze changed")
    if sha256_file(development) != identities["development"]:
        raise ReplayBootstrapError("Development data changed")
    if sha256_file(canonical) != identities["canonical"]:
        raise ReplayBootstrapError("Canonical data changed")
    verify_zero_original_progress(original_progress, expected_sha=identities["original_progress"])
    if directory_snapshot(frozen_evidence) != frozen_snapshot_before:
        raise ReplayBootstrapError("frozen component evidence changed")

    summary = {
        "schema_version": "phase7-canonical-replay-bootstrap/v1",
        "status": "PASS",
        "pr355_head": head,
        "critical_blobs": EXPECTED_PR_BLOBS,
        "derived_runner_sha256": derived_sha,
        "component_count": evidence["components"],
        "trial_count": evidence["trials"],
        "canonical_hashes": evidence["canonical_hashes"],
        "mlforecast_version": mlforecast_version,
        "holdout_draws_accessed": 0,
        "actuals_accessed": 0,
        "holdout_executed": False,
        "sealed_inputs_unchanged": True,
        "original_phase7_state_unchanged": True,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output_root / "REPLAY_BOOTSTRAP_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksum_path = output_root / "SHA256SUMS"
    files = sorted(
        path for path in output_root.rglob("*") if path.is_file() and path != checksum_path
    )
    checksum_path.write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output_root)}\n" for path in files
        ),
        encoding="ascii",
    )

    print("ALL_4_SEED_CANONICAL_MATCH=PASS")
    print("ALL_80_TRIALS_REPLAYED=PASS")
    print("HOLDOUT_DRAWS_ACCESSED=0")
    print("ACTUALS_ACCESSED=0")
    print("HOLDOUT_EXECUTED=NO")
    print("SEALED_INPUTS_UNCHANGED=PASS")
    print("ORIGINAL_PHASE7_STATE_UNCHANGED=PASS")
    print("SHA256SUMS_CREATED=YES")
    print("SAFE_TO_REVIEW_REPLAY_EVIDENCE=YES")
    print("SAFE_TO_EXECUTE_HOLDOUT=NO")
    print("STATUS=PASS")
    print(f"REPLAY_ROOT={output_root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch only PR #355 critical files and run the pinned 4-seed/80-trial "
            "Replay-only verification without checking out Windows-invalid repository paths."
        )
    )
    parser.add_argument("--repo", type=Path, default=repo_root())
    parser.add_argument("--output-root", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = (args.output_root or default_output_root()).resolve()
    try:
        return run_replay(repo=args.repo.resolve(), output_root=output_root)
    except Exception as exc:
        print(f"STATUS=BLOCKED")
        print(f"ERROR={exc}")
        print("SAFE_TO_EXECUTE_HOLDOUT=NO")
        print(f"REPLAY_ROOT={output_root}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
