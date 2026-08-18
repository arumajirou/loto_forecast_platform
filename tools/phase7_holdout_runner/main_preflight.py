from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

SCIENTIFIC_MAIN_ANCESTOR: Final = "e3b05bec7382c4571f4b1a05df054eda5f6d99fb"
EXPECTED_SEMANTIC_BLOB: Final = "257d4d4a88e56f6070200a67fd86b2beca73a3c1"
EXPECTED_DERIVER_BLOB: Final = "efa988d671cb31820d4a4292498dd034c85ce481"
EXPECTED_ORIGINAL_RUNNER_SHA256: Final = (
    "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
)
EXPECTED_DERIVED_RUNNER_SHA256: Final = (
    "8077ccf023f9100344206f588dadae655eb828f3529c4d4d83ebf89c9c1ee074"
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
SEMANTIC_PATH: Final = "src/loto/evaluation/semantic_config.py"
DERIVER_PATH: Final = "tools/phase7_holdout_runner/derive_canonical_runner.py"


class PreflightError(RuntimeError):
    """Raised when merged-main Phase 7 safety cannot be proven."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(
    repo_root: Path,
    *args: str,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=text,
        check=False,
    )


def git_text(repo_root: Path, *args: str) -> str:
    run = run_git(repo_root, *args)
    if run.returncode != 0:
        raise PreflightError(
            f"git {' '.join(args)} failed rc={run.returncode}: {run.stderr.strip()}"
        )
    return run.stdout.strip()


def git_blob(repo_root: Path, path: str) -> str:
    return git_text(repo_root, "rev-parse", f"HEAD:{path}")


def materialize_git_file(repo_root: Path, path: str, destination: Path) -> None:
    run = run_git(repo_root, "show", f"HEAD:{path}", text=False)
    if run.returncode != 0:
        stderr = run.stderr.decode("utf-8", errors="replace").strip()
        raise PreflightError(f"git show failed path={path}: {stderr}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(run.stdout)


def resolve_canonical(pointer: Path) -> Path:
    for line in pointer.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            return Path(text)
    raise PreflightError(f"canonical pointer is empty: {pointer}")


def read_progress(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PreflightError(f"progress payload is not an object: {path}")
    return payload


def require_zero_progress(progress: dict[str, Any]) -> str:
    state = progress.get("state", progress.get("phase"))
    if state != "REPLAY_VERIFICATION":
        raise PreflightError(f"unexpected original Phase7 state: {state!r}")
    if int(progress.get("holdout_draws_done", 0)) != 0:
        raise PreflightError("original Phase7 Holdout draws are nonzero")
    if int(progress.get("actuals_accessed", 0)) != 0:
        raise PreflightError("original Phase7 actual access is nonzero")
    return str(state)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_output_root() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"phase7-merged-main-preflight-{stamp}"


def assert_identity(path: Path, expected_sha256: str, label: str) -> str:
    if not path.is_file():
        raise PreflightError(f"{label} missing: {path}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise PreflightError(
            f"{label} SHA mismatch: expected={expected_sha256} actual={actual}"
        )
    return actual


def ensure_no_existing_locks(artifacts: Path) -> None:
    lock_root = artifacts / "prediction_locks"
    if lock_root.exists() and any(path.is_file() for path in lock_root.rglob("*")):
        raise PreflightError("prediction lock files already exist in original Phase7 artifacts")
    chain = artifacts / "SEQUENTIAL_LOCK_CHAIN.jsonl"
    if chain.exists():
        raise PreflightError(f"sequential lock chain already exists: {chain}")


def write_sha256sums(output_root: Path) -> None:
    checksum_path = output_root / "SHA256SUMS"
    files = sorted(
        path
        for path in output_root.rglob("*")
        if path.is_file() and path != checksum_path
    )
    checksum_path.write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output_root)}\n"
            for path in files
        ),
        encoding="ascii",
    )


def run_preflight(*, repo_root: Path, output_root: Path) -> dict[str, Any]:
    ancestor = run_git(
        repo_root,
        "merge-base",
        "--is-ancestor",
        SCIENTIFIC_MAIN_ANCESTOR,
        "HEAD",
    )
    if ancestor.returncode != 0:
        raise PreflightError(
            "merged scientific main commit is not an ancestor of local HEAD: "
            f"{SCIENTIFIC_MAIN_ANCESTOR}"
        )

    head_sha = git_text(repo_root, "rev-parse", "HEAD")
    head_tree = git_text(repo_root, "rev-parse", "HEAD^{tree}")
    semantic_blob = git_blob(repo_root, SEMANTIC_PATH)
    deriver_blob = git_blob(repo_root, DERIVER_PATH)
    if semantic_blob != EXPECTED_SEMANTIC_BLOB:
        raise PreflightError(
            "merged-main semantic blob mismatch: "
            f"expected={EXPECTED_SEMANTIC_BLOB} actual={semantic_blob}"
        )
    if deriver_blob != EXPECTED_DERIVER_BLOB:
        raise PreflightError(
            "merged-main deriver blob mismatch: "
            f"expected={EXPECTED_DERIVER_BLOB} actual={deriver_blob}"
        )

    downloads = Path.home() / "Downloads"
    phase7_root = downloads / "automlforecast-phase7-holdout-20260818-101611"
    phase6c_root = downloads / "automlforecast-phase6c-ensemble-freeze-20260818-101021"
    phase3_root = downloads / "automlforecast-phase3-input-size-20260817-173808"

    original_runner = phase7_root / "phase7_holdout.py"
    artifacts = phase7_root / "artifacts"
    progress_path = artifacts / "progress.json"
    freeze_path = phase6c_root / "artifacts" / "CANDIDATE_FREEZE.json"
    development = phase3_root / "artifacts" / "numbers3-development-only.csv"
    canonical_pointer = downloads / "numbers3-current-canonical-path.txt"

    original_runner_sha = assert_identity(
        original_runner,
        EXPECTED_ORIGINAL_RUNNER_SHA256,
        "sealed original runner",
    )
    freeze_sha = assert_identity(freeze_path, EXPECTED_FREEZE_SHA256, "Candidate Freeze")
    development_sha = assert_identity(
        development,
        EXPECTED_DEVELOPMENT_SHA256,
        "Development data",
    )
    if not canonical_pointer.is_file():
        raise PreflightError(f"canonical pointer missing: {canonical_pointer}")
    canonical = resolve_canonical(canonical_pointer)
    canonical_sha = assert_identity(
        canonical,
        EXPECTED_CANONICAL_SHA256,
        "canonical data identity",
    )
    if not progress_path.is_file():
        raise PreflightError(f"original Phase7 progress missing: {progress_path}")

    progress_before_sha = sha256_file(progress_path)
    progress_before = read_progress(progress_path)
    state = require_zero_progress(progress_before)
    ensure_no_existing_locks(artifacts)

    output_root.mkdir(parents=True, exist_ok=False)
    source_root = output_root / "source_snapshot"
    semantic_source = source_root / "semantic_config.py"
    deriver_source = source_root / "derive_canonical_runner.py"
    materialize_git_file(repo_root, SEMANTIC_PATH, semantic_source)
    materialize_git_file(repo_root, DERIVER_PATH, deriver_source)

    bundle = output_root / "derived_bundle"
    derive = subprocess.run(
        [
            sys.executable,
            str(deriver_source),
            "--runner",
            str(original_runner),
            "--semantic-config-source",
            str(semantic_source),
            "--output-dir",
            str(bundle),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    (output_root / "derive.stdout.log").write_text(derive.stdout, encoding="utf-8")
    (output_root / "derive.stderr.log").write_text(derive.stderr, encoding="utf-8")
    if derive.returncode != 0:
        raise PreflightError(f"merged-main runner derivation failed rc={derive.returncode}")

    derived_runner = bundle / "phase7_holdout_canonical_v1.py"
    if not derived_runner.is_file():
        raise PreflightError(f"derived runner missing: {derived_runner}")
    derived_sha = sha256_file(derived_runner)
    if derived_sha != EXPECTED_DERIVED_RUNNER_SHA256:
        raise PreflightError(
            "derived runner SHA mismatch: "
            f"expected={EXPECTED_DERIVED_RUNNER_SHA256} actual={derived_sha}"
        )
    py_compile.compile(str(derived_runner), doraise=True)

    current_identities = {
        "original_runner": sha256_file(original_runner),
        "freeze": sha256_file(freeze_path),
        "development": sha256_file(development),
        "canonical": sha256_file(canonical),
        "progress": sha256_file(progress_path),
    }
    expected_unchanged = {
        "original_runner": original_runner_sha,
        "freeze": freeze_sha,
        "development": development_sha,
        "canonical": canonical_sha,
        "progress": progress_before_sha,
    }
    if current_identities != expected_unchanged:
        raise PreflightError("sealed input or progress changed during merged-main preflight")

    progress_after = read_progress(progress_path)
    require_zero_progress(progress_after)
    ensure_no_existing_locks(artifacts)

    report = {
        "schema_version": "phase7-merged-main-preflight/v1",
        "status": "PASS",
        "main_head_sha": head_sha,
        "main_tree_sha": head_tree,
        "scientific_main_ancestor": SCIENTIFIC_MAIN_ANCESTOR,
        "semantic_blob": semantic_blob,
        "deriver_blob": deriver_blob,
        "sealed_original_runner_sha256": original_runner_sha,
        "derived_runner_sha256": derived_sha,
        "candidate_freeze_sha256": freeze_sha,
        "development_sha256": development_sha,
        "canonical_sha256": canonical_sha,
        "original_phase7_state": state,
        "holdout_draws_accessed": 0,
        "actuals_accessed": 0,
        "holdout_executed": False,
        "prediction_lock_created": False,
        "sealed_inputs_unchanged": True,
        "original_phase7_state_unchanged": True,
        "safe_to_execute_holdout": True,
        "safe_to_read_actuals_before_prediction_lock": False,
    }
    (output_root / "MERGED_MAIN_PREFLIGHT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_sha256sums(output_root)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify merged-main Phase 7 identities and deterministically derive the "
            "canonical runner without executing Holdout or accessing actuals."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=default_repo_root())
    parser.add_argument("--output-root", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root or default_output_root()
    report = run_preflight(
        repo_root=args.repo_root.resolve(),
        output_root=output_root.resolve(),
    )
    print(f"PREFLIGHT_ROOT={output_root}")
    print(f"MAIN_HEAD_SHA={report['main_head_sha']}")
    print(f"MAIN_TREE_SHA={report['main_tree_sha']}")
    print(f"SEMANTIC_BLOB=PASS sha={report['semantic_blob']}")
    print(f"DERIVER_BLOB=PASS sha={report['deriver_blob']}")
    print(
        "SEALED_ORIGINAL_RUNNER=PASS "
        f"sha256={report['sealed_original_runner_sha256']}"
    )
    print(f"DERIVED_RUNNER=PASS sha256={report['derived_runner_sha256']}")
    print(f"CANDIDATE_FREEZE=PASS sha256={report['candidate_freeze_sha256']}")
    print(f"DEVELOPMENT=PASS sha256={report['development_sha256']}")
    print(f"CANONICAL_IDENTITY=PASS sha256={report['canonical_sha256']}")
    print(f"ORIGINAL_PHASE7_STATE={report['original_phase7_state']}")
    print("SEALED_INPUTS_UNCHANGED=PASS")
    print("ORIGINAL_PHASE7_STATE_UNCHANGED=PASS")
    print("HOLDOUT_DRAWS_ACCESSED=0")
    print("ACTUALS_ACCESSED=0")
    print("HOLDOUT_EXECUTED=NO")
    print("PREDICTION_LOCK_CREATED=NO")
    print("SAFE_TO_READ_ACTUALS_BEFORE_PREDICTION_LOCK=NO")
    print("SAFE_TO_EXECUTE_HOLDOUT=YES")
    print("SHA256SUMS_CREATED=YES")
    print("STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
