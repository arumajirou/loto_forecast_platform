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

EXPECTED_ORIGINAL_RUNNER_SHA256: Final = (
    "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
)
EXPECTED_BASE_DERIVED_SHA256: Final = (
    "8077ccf023f9100344206f588dadae655eb828f3529c4d4d83ebf89c9c1ee074"
)
EXPECTED_FREEZE_SHA256: Final = "deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c"
EXPECTED_DEVELOPMENT_SHA256: Final = (
    "f6e0292347cd03acea95b5c788eaa51436a8b9e7e42d2fc000e9b9d366e2557e"
)
EXPECTED_CANONICAL_SHA256: Final = (
    "88fd7bf24d2864fce74e95bf6475ff4b0292446f1354d403105970d095d6592f"
)
SCIENTIFIC_GIT_COMMIT: Final = "179bcbc9a51a60f0badfe7faa25f3818ab686229"


class DiagnosticError(RuntimeError):
    """Raised when the live mapping-key diagnostic cannot be proven safe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_downloads() -> Path:
    return Path.home() / "Downloads"


def default_output_root() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return default_downloads() / f"phase7-live-mapping-diagnostic-{stamp}"


def diagnostic_runner_path(bundle: Path) -> Path:
    """Keep the diagnostic runner beside the derived semantic module for imports."""
    return bundle / "phase7_holdout_mapping_diagnostic.py"


def collect_non_string_mapping_keys(value: Any, path: str = "$") -> list[dict[str, str]]:
    """Return typed paths for non-string dict keys without mutating the input."""
    findings: list[dict[str, str]] = []

    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                child = path + "[" + json.dumps(key, ensure_ascii=False) + "]"
            else:
                findings.append(
                    {
                        "mapping_path": path,
                        "key_type": type(key).__name__,
                        "key_repr": repr(key),
                        "value_type": type(item).__name__,
                    }
                )
                child = path + "[" + repr(key) + "]"
            findings.extend(collect_non_string_mapping_keys(item, child))
        return findings

    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings.extend(collect_non_string_mapping_keys(item, f"{path}[{index}]"))

    return findings


def patch_runner_for_mapping_diagnostic(source: str) -> str:
    """Inject a fail-closed path diagnostic before canonical replay hashing."""
    anchor = """    canonical_replay_hash = (
        canonical_semantic_sha256_v1(
            best_config,
            legacy_object_states=
                legacy_object_states,
        )
    )
"""

    diagnostic = (
        """    def _collect_non_string_mapping_keys(value, path="$"):
        findings = []
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(key, str):
                    child = path + "[" + json.dumps(key, ensure_ascii=False) + "]"
                else:
                    findings.append(
                        {
                            "mapping_path": path,
                            "key_type": type(key).__name__,
                            "key_repr": repr(key),
                            "value_type": type(item).__name__,
                        }
                    )
                    child = path + "[" + repr(key) + "]"
                findings.extend(
                    _collect_non_string_mapping_keys(item, child)
                )
            return findings
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                findings.extend(
                    _collect_non_string_mapping_keys(
                        item, f"{path}[{index}]"
                    )
                )
        return findings

    mapping_key_findings = _collect_non_string_mapping_keys(
        best_config
    )
    if mapping_key_findings:
        diagnostic_path = (
            replay_dir
            / f"AutoCatboost__seed{seed}__MAPPING_KEY_DIAGNOSTIC.json"
        )
        atomic_json(
            diagnostic_path,
            {
                "schema_version":
                    "phase7-live-mapping-key-diagnostic/v1",
                "status":
                    "CAPTURED",
                "seed":
                    seed,
                "findings":
                    mapping_key_findings,
                "holdout_draws_accessed":
                    0,
                "actuals_accessed":
                    0,
                "holdout_executed":
                    False,
                "captured_at_utc":
                    now(),
            },
        )
        first = mapping_key_findings[0]
        raise RuntimeError(
            "live best_config non-string mapping key "
            f"seed={seed} path={first['mapping_path']} "
            f"key_type={first['key_type']} "
            f"key={first['key_repr']}"
        )

"""
        + anchor
    )

    count = source.count(anchor)
    if count != 1:
        raise DiagnosticError(f"canonical replay hash anchor count={count}; expected exactly 1")
    return source.replace(anchor, diagnostic, 1)


def read_progress(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DiagnosticError(f"progress payload is not an object: {path}")
    return payload


def require_zero_holdout(progress: dict[str, Any], *, label: str) -> None:
    if int(progress.get("holdout_draws_done", 0)) != 0:
        raise DiagnosticError(f"{label} Holdout draws are nonzero")
    if int(progress.get("actuals_accessed", 0)) != 0:
        raise DiagnosticError(f"{label} actual access is nonzero")


def resolve_canonical(pointer: Path) -> Path:
    for line in pointer.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            return Path(text)
    raise DiagnosticError(f"canonical pointer is empty: {pointer}")


def run_diagnostic(*, repo_root: Path, output_root: Path) -> dict[str, Any]:
    downloads = default_downloads()
    original_phase7_root = downloads / "automlforecast-phase7-holdout-20260818-101611"
    original_runner = original_phase7_root / "phase7_holdout.py"
    original_progress = original_phase7_root / "artifacts" / "progress.json"
    phase6c_root = downloads / "automlforecast-phase6c-ensemble-freeze-20260818-101021"
    freeze_path = phase6c_root / "artifacts" / "CANDIDATE_FREEZE.json"
    development = (
        downloads
        / "automlforecast-phase3-input-size-20260817-173808"
        / "artifacts"
        / "numbers3-development-only.csv"
    )
    canonical_pointer = downloads / "numbers3-current-canonical-path.txt"
    semantic_source = repo_root / "src" / "loto" / "evaluation" / "semantic_config.py"
    deriver = repo_root / "tools" / "phase7_holdout_runner" / "derive_canonical_runner.py"

    required_files = (
        original_runner,
        original_progress,
        freeze_path,
        development,
        canonical_pointer,
        semantic_source,
        deriver,
    )
    for path in required_files:
        if not path.is_file():
            raise DiagnosticError(f"required file missing: {path}")

    canonical = resolve_canonical(canonical_pointer)
    if not canonical.is_file():
        raise DiagnosticError(f"canonical file missing: {canonical}")

    identities = {
        "original_runner": sha256_file(original_runner),
        "freeze": sha256_file(freeze_path),
        "development": sha256_file(development),
        "canonical": sha256_file(canonical),
        "original_progress": sha256_file(original_progress),
    }
    expected = {
        "original_runner": EXPECTED_ORIGINAL_RUNNER_SHA256,
        "freeze": EXPECTED_FREEZE_SHA256,
        "development": EXPECTED_DEVELOPMENT_SHA256,
        "canonical": EXPECTED_CANONICAL_SHA256,
    }
    for key, expected_sha in expected.items():
        if identities[key] != expected_sha:
            raise DiagnosticError(
                f"{key} SHA mismatch: expected={expected_sha} actual={identities[key]}"
            )

    progress_before = read_progress(original_progress)
    require_zero_holdout(progress_before, label="original Phase7 before diagnostic")

    output_root.mkdir(parents=True, exist_ok=False)
    bundle = output_root / "derived_bundle"
    artifacts = output_root / "artifacts"
    stdout_path = output_root / "replay.stdout.log"
    stderr_path = output_root / "replay.stderr.log"

    derive = subprocess.run(
        [
            sys.executable,
            str(deriver),
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
        raise DiagnosticError(f"runner derivation failed rc={derive.returncode}")

    base_runner = bundle / "phase7_holdout_canonical_v1.py"
    if sha256_file(base_runner) != EXPECTED_BASE_DERIVED_SHA256:
        raise DiagnosticError(
            "base derived runner SHA mismatch: "
            f"expected={EXPECTED_BASE_DERIVED_SHA256} actual={sha256_file(base_runner)}"
        )

    source = base_runner.read_text(encoding="utf-8")
    diagnostic_source = patch_runner_for_mapping_diagnostic(source)
    diagnostic_runner = diagnostic_runner_path(bundle)
    diagnostic_runner.write_text(diagnostic_source, encoding="utf-8", newline="\n")
    py_compile.compile(str(diagnostic_runner), doraise=True)

    run = subprocess.run(
        [
            sys.executable,
            str(diagnostic_runner),
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
        capture_output=True,
        text=True,
        check=False,
        env={
            **dict(__import__("os").environ),
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
    )
    stdout_path.write_text(run.stdout, encoding="utf-8")
    stderr_path.write_text(run.stderr, encoding="utf-8")

    replay_dir = artifacts / "replay_verification"
    diagnostic_files = sorted(replay_dir.glob("*__MAPPING_KEY_DIAGNOSTIC.json"))

    progress_after = read_progress(original_progress)
    require_zero_holdout(progress_after, label="original Phase7 after diagnostic")
    if sha256_file(original_progress) != identities["original_progress"]:
        raise DiagnosticError("original Phase7 progress changed during diagnostic")

    if sha256_file(original_runner) != identities["original_runner"]:
        raise DiagnosticError("original runner changed during diagnostic")
    if sha256_file(freeze_path) != identities["freeze"]:
        raise DiagnosticError("Candidate Freeze changed during diagnostic")
    if sha256_file(development) != identities["development"]:
        raise DiagnosticError("Development data changed during diagnostic")
    if sha256_file(canonical) != identities["canonical"]:
        raise DiagnosticError("Canonical data changed during diagnostic")

    lock_files = list(artifacts.glob("prediction_locks/**/*"))
    chain = artifacts / "SEQUENTIAL_LOCK_CHAIN.jsonl"
    if any(path.is_file() for path in lock_files) or chain.exists():
        raise DiagnosticError("Holdout lock artifacts detected during diagnostic")

    findings: list[dict[str, Any]] = []
    for path in diagnostic_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise DiagnosticError(f"invalid diagnostic artifact: {path}")
        findings.append(payload)

    if findings:
        for payload in findings:
            if int(payload.get("holdout_draws_accessed", -1)) != 0:
                raise DiagnosticError("diagnostic artifact reports Holdout access")
            if int(payload.get("actuals_accessed", -1)) != 0:
                raise DiagnosticError("diagnostic artifact reports actual access")
            if payload.get("holdout_executed") is not False:
                raise DiagnosticError("diagnostic artifact reports Holdout execution")
        status = "DIAGNOSTIC_CAPTURED"
    elif run.returncode == 0:
        status = "REPLAY_ONLY_PASSED_WITHOUT_NON_STRING_KEYS"
    else:
        stderr_tail = "\n".join(run.stderr.splitlines()[-80:])
        raise DiagnosticError(
            "replay failed without mapping-key diagnostic artifact; "
            f"rc={run.returncode}; stderr tail follows:\n{stderr_tail}"
        )

    summary = {
        "schema_version": "phase7-live-mapping-key-diagnostic-run/v1",
        "status": status,
        "runner_return_code": run.returncode,
        "base_derived_runner_sha256": EXPECTED_BASE_DERIVED_SHA256,
        "diagnostic_runner_sha256": sha256_file(diagnostic_runner),
        "diagnostic_artifact_count": len(findings),
        "diagnostics": findings,
        "holdout_draws_accessed": 0,
        "actuals_accessed": 0,
        "holdout_executed": False,
        "sealed_inputs_unchanged": True,
        "original_phase7_state_unchanged": True,
    }
    summary_path = output_root / "LIVE_MAPPING_KEY_DIAGNOSTIC_SUMMARY.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksum_path = output_root / "SHA256SUMS"
    output_files = sorted(
        path for path in output_root.rglob("*") if path.is_file() and path != checksum_path
    )
    checksum_path.write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(output_root)}\n" for path in output_files),
        encoding="ascii",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive a diagnostic-only Phase 7 runner, capture live non-string mapping-key "
            "paths, and stop before Holdout."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=default_repo_root())
    parser.add_argument("--output-root", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root or default_output_root()
    summary = run_diagnostic(repo_root=args.repo_root, output_root=output_root)

    print(f"DIAGNOSTIC_ROOT={output_root}")
    print(f"STATUS={summary['status']}")
    print(f"RUNNER_RC={summary['runner_return_code']}")
    print(f"DIAGNOSTIC_ARTIFACT_COUNT={summary['diagnostic_artifact_count']}")
    for artifact in summary["diagnostics"]:
        seed = artifact.get("seed")
        for finding in artifact.get("findings", []):
            print(
                "LIVE_NON_STRING_KEY "
                f"seed={seed} "
                f"path={finding.get('mapping_path')} "
                f"key_type={finding.get('key_type')} "
                f"key={finding.get('key_repr')} "
                f"value_type={finding.get('value_type')}"
            )
    print("SEALED_INPUTS_UNCHANGED=PASS")
    print("ORIGINAL_PHASE7_STATE_UNCHANGED=PASS")
    print("HOLDOUT_DRAWS_ACCESSED=0")
    print("ACTUALS_ACCESSED=0")
    print("HOLDOUT_EXECUTED=NO")
    print("SAFE_TO_PATCH_SERIALIZER=NO")
    print("SAFE_TO_EXECUTE_HOLDOUT=NO")
    print("SHA256SUMS_CREATED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
