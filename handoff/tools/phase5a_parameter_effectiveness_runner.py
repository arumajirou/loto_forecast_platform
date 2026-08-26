#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(os.environ.get("LOTO_ROOT", "/mnt/e/env/ts/loto_forecast_platform"))
SOURCE_WT = Path(
    os.environ.get(
        "LOTO_SOURCE_WT",
        "/mnt/e/env/ts/worktrees/loto-runtime-audit-20260826-121248",
    )
)
HANDOFF_WT = Path(
    os.environ.get(
        "LOTO_HANDOFF_WT",
        "/mnt/e/env/ts/worktrees/loto-runtime-handoff",
    )
)
HANDOFF = HANDOFF_WT / "handoff"
BRANCH = "ops/runtime-audit-handoff"
EXPECTED_SOURCE_SHA = "0a13c287e0f0fcc8f983be3512654524dad18b2c"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase5a-parameter-effectiveness-{RUN_ID}"
HANDOFF_OUT = HANDOFF / "phase5a"
SPEC = SOURCE_WT / "examples/parameter_effectiveness/cross_platform_smoke.json"
TEST_DIR = SOURCE_WT / "tests/parameter_effectiveness"
EVIDENCE = LOCAL_OUT / "evidence"

EXPECTED_PROBES = {
    "mlforecast-num-samples-trial-count": {
        "library": "mlforecast",
        "model": "AutoLinearRegression",
        "parameter": "num_samples",
        "surface": "trial_count",
        "relation": "increase",
    },
    "statsforecast-season-length-prediction": {
        "library": "statsforecast",
        "model": "SeasonalNaive",
        "parameter": "season_length",
        "surface": "prediction",
        "relation": "change",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def git_output(args: list[str]) -> str:
    proc = run(["git", "-C", str(HANDOFF_WT), *args], timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def source_git_output(args: list[str]) -> str:
    proc = run(["git", "-C", str(SOURCE_WT), *args], timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"source git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def source_gate() -> dict[str, str | None]:
    head = source_git_output(["rev-parse", "HEAD"])
    if head != EXPECTED_SOURCE_SHA:
        raise RuntimeError(
            f"SOURCE_SHA_GATE_FAILED:expected={EXPECTED_SOURCE_SHA}:actual={head}"
        )
    if source_git_output(["status", "--porcelain"]):
        raise RuntimeError("SOURCE_WORKTREE_DIRTY")

    pyproject = SOURCE_WT / "pyproject.toml"
    uv_lock = SOURCE_WT / "uv.lock"
    if not pyproject.is_file():
        raise RuntimeError("SOURCE_PYPROJECT_MISSING")
    return {
        "source_sha": head,
        "pyproject_sha256": sha256_file(pyproject),
        "uv_lock_sha256": sha256_file(uv_lock) if uv_lock.is_file() else None,
    }


def handoff_sync() -> None:
    if git_output(["branch", "--show-current"]) != BRANCH:
        raise RuntimeError("HANDOFF_BRANCH_GATE_FAILED")
    if git_output(["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_WORKTREE_DIRTY")
    git_output(["fetch", "--prune", "origin"])
    proc = run(
        ["git", "-C", str(HANDOFF_WT), "pull", "--ff-only", "origin", BRANCH],
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"HANDOFF_PULL_FAILED:{proc.stderr.strip()}")


def prerequisite_gate() -> dict[str, Any]:
    phase4h_path = HANDOFF / "phase4h/summary.json"
    if not phase4h_path.is_file():
        raise RuntimeError("PHASE4H_SUMMARY_MISSING")
    phase4h = json.loads(phase4h_path.read_text("utf-8"))
    if phase4h.get("status") != "VERIFIED":
        raise RuntimeError("PHASE4H_NOT_VERIFIED")
    if phase4h.get("source_sha") != EXPECTED_SOURCE_SHA:
        raise RuntimeError(
            "PHASE4H_SOURCE_SHA_MISMATCH:"
            f"expected={EXPECTED_SOURCE_SHA}:actual={phase4h.get('source_sha')}"
        )
    if phase4h.get("formal_runtime_certification") is not True:
        raise RuntimeError("PHASE4H_FORMAL_RUNTIME_CERTIFICATION_MISSING")
    return phase4h


def candidate_runtimes() -> list[Path]:
    candidates: list[Path] = [
        ROOT / ".venv/bin/python",
        SOURCE_WT / ".venv/bin/python",
    ]
    candidates.extend(sorted(ROOT.glob("environments/*/.venv/bin/python")))
    candidates.extend(sorted(ROOT.glob(".runtime-envs/*/bin/python")))

    seen: set[str] = set()
    output: list[Path] = []
    for path in candidates:
        key = str(path)
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        output.append(path)
    return output


def probe_runtime(path: Path) -> dict[str, Any]:
    code = r'''
import importlib.metadata as md
import json
import platform
import sys

payload = {
    "python": platform.python_version(),
    "executable": sys.executable,
}
try:
    import mlforecast
    import statsforecast
    import optuna
    import numpy
    import pandas
    import pydantic
    import pytest
    import sklearn
    payload.update({
        "status": "PASS",
        "mlforecast": md.version("mlforecast"),
        "statsforecast": md.version("statsforecast"),
        "optuna": md.version("optuna"),
        "numpy": md.version("numpy"),
        "pandas": md.version("pandas"),
        "pydantic": md.version("pydantic"),
        "pytest": md.version("pytest"),
        "scikit_learn": md.version("scikit-learn"),
    })
except Exception as exc:
    payload.update({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
print(json.dumps(payload, sort_keys=True))
'''
    proc = run([str(path), "-c", code], timeout=60)
    row: dict[str, Any] = {
        "candidate": str(path),
        "returncode": proc.returncode,
        "stderr": proc.stderr.strip(),
    }
    if proc.returncode != 0:
        row.update({"status": "FAIL", "error": proc.stderr.strip() or "probe failed"})
        return row
    try:
        row.update(json.loads(proc.stdout.strip().splitlines()[-1]))
    except Exception as exc:
        row.update({"status": "FAIL", "error": f"JSONDecodeError: {exc}"})
    return row


def runtime_compatible(row: dict[str, Any]) -> bool:
    if row.get("status") != "PASS":
        return False
    python = str(row.get("python", ""))
    if not python.startswith("3.13."):
        return False
    if row.get("mlforecast") != "1.1.0":
        return False
    if row.get("statsforecast") != "2.1.1":
        return False
    optuna = str(row.get("optuna", ""))
    return optuna.startswith("4.")


def select_runtime() -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    probes = [probe_runtime(path) for path in candidate_runtimes()]
    dump_json(LOCAL_OUT / "runtime-candidates.json", probes)
    compatible = [row for row in probes if runtime_compatible(row)]
    if not compatible:
        raise RuntimeError(
            "NO_EXISTING_PHASE5A_RUNTIME:requires Python3.13 + mlforecast1.1.0 + "
            "statsforecast2.1.1 + optuna4.x"
        )
    preferred = sorted(
        compatible,
        key=lambda row: (
            0 if row.get("candidate") == str(ROOT / ".venv/bin/python") else 1,
            len(str(row.get("candidate"))),
            str(row.get("candidate")),
        ),
    )[0]
    return Path(str(preferred["candidate"])), preferred, probes


def execution_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SOURCE_WT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(LOCAL_OUT / "pycache"),
            "LOTO_REQUIRE_REAL_PARAMETER_ADAPTERS": "1",
            "CUDA_VISIBLE_DEVICES": "",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    return env


def run_focused_tests(runtime: Path) -> dict[str, Any]:
    proc = run(
        [
            str(runtime),
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            str(TEST_DIR),
            "-q",
        ],
        cwd=SOURCE_WT,
        timeout=1800,
        env=execution_env(),
    )
    (LOCAL_OUT / "pytest.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "pytest.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(
            f"PHASE5A_FOCUSED_PYTEST_FAILED:rc={proc.returncode}:"
            f"{proc.stderr[-2000:]}"
        )
    return {"returncode": proc.returncode, "stdout_tail": proc.stdout[-2000:]}


def run_suite(runtime: Path) -> dict[str, Any]:
    if EVIDENCE.exists():
        shutil.rmtree(EVIDENCE)
    proc = run(
        [
            str(runtime),
            "-m",
            "loto.parameter_effectiveness.cli",
            "--spec",
            str(SPEC),
            "--output",
            str(EVIDENCE),
        ],
        cwd=SOURCE_WT,
        timeout=1800,
        env=execution_env(),
    )
    (LOCAL_OUT / "suite.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "suite.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(
            f"PHASE5A_SUITE_FAILED:rc={proc.returncode}:{proc.stderr[-2000:]}"
        )
    return {"returncode": proc.returncode, "stdout_tail": proc.stdout[-4000:]}


def verify_evidence() -> dict[str, Any]:
    required = {
        "suite.json",
        "results.json",
        "summary.csv",
        "environment.json",
        "manifest.json",
        "SHA256SUMS",
    }
    observed = {path.name for path in EVIDENCE.iterdir() if path.is_file()}
    missing = sorted(required - observed)
    if missing:
        raise RuntimeError(f"PHASE5A_EVIDENCE_FILES_MISSING:{missing}")

    checksum_rows: list[dict[str, Any]] = []
    for line in (EVIDENCE / "SHA256SUMS").read_text("utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        name = name.strip()
        path = EVIDENCE / name
        if not path.is_file():
            raise RuntimeError(f"PHASE5A_CHECKSUM_FILE_MISSING:{name}")
        actual = sha256_file(path)
        checksum_rows.append({"path": name, "expected": digest, "actual": actual})
        if actual != digest:
            raise RuntimeError(
                f"PHASE5A_CHECKSUM_MISMATCH:{name}:expected={digest}:actual={actual}"
            )

    suite = json.loads((EVIDENCE / "suite.json").read_text("utf-8"))
    environment = json.loads((EVIDENCE / "environment.json").read_text("utf-8"))
    results = json.loads((EVIDENCE / "results.json").read_text("utf-8"))
    manifest = json.loads((EVIDENCE / "manifest.json").read_text("utf-8"))

    if suite.get("metadata", {}).get("holdout_evaluated") is not False:
        raise RuntimeError("PHASE5A_SUITE_HOLDOUT_POLICY_VIOLATION")
    if suite.get("metadata", {}).get("prospective_evaluated") is not False:
        raise RuntimeError("PHASE5A_SUITE_PROSPECTIVE_POLICY_VIOLATION")
    if environment.get("holdout_evaluated") is not False:
        raise RuntimeError("PHASE5A_ENV_HOLDOUT_POLICY_VIOLATION")
    if environment.get("prospective_evaluated") is not False:
        raise RuntimeError("PHASE5A_ENV_PROSPECTIVE_POLICY_VIOLATION")

    if not isinstance(results, list) or len(results) != len(EXPECTED_PROBES):
        raise RuntimeError(
            f"PHASE5A_RESULT_COUNT_MISMATCH:expected={len(EXPECTED_PROBES)}:"
            f"actual={len(results) if isinstance(results, list) else 'non-list'}"
        )

    checks: dict[str, bool] = {
        "result_count": len(results) == 2,
        "holdout_not_evaluated": True,
        "prospective_not_evaluated": True,
        "evidence_checksums_valid": True,
    }
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in results:
        probe_id = str(row.get("probe_id"))
        expected = EXPECTED_PROBES.get(probe_id)
        if expected is None:
            raise RuntimeError(f"PHASE5A_UNEXPECTED_PROBE:{probe_id}")
        if probe_id in seen:
            raise RuntimeError(f"PHASE5A_DUPLICATE_PROBE:{probe_id}")
        seen.add(probe_id)

        row_checks = {
            "library": row.get("library") == expected["library"],
            "model": row.get("model") == expected["model"],
            "parameter": row.get("parameter") == expected["parameter"],
            "surface": row.get("expected_surface") == expected["surface"],
            "relation": row.get("expected_relation") == expected["relation"],
            "outcome_effective": row.get("outcome") == "effective",
            "supported": row.get("supported") is True,
            "pairs_total": row.get("pairs_total") == 2,
            "pairs_eligible": row.get("pairs_eligible") == 2,
            "pairs_matched": row.get("pairs_matched") == 2,
            "pairs_failed": row.get("pairs_failed") == 0,
            "matched_fraction": row.get("matched_fraction") == 1.0,
            "holdout_not_evaluated": row.get("holdout_evaluated") is False,
            "prospective_not_evaluated": row.get("prospective_evaluated") is False,
        }
        if not all(row_checks.values()):
            failed = [key for key, value in row_checks.items() if not value]
            raise RuntimeError(f"PHASE5A_PROBE_VALIDATION_FAILED:{probe_id}:{failed}")
        checks[f"{probe_id}_effective"] = True
        normalized.append(
            {
                "probe_id": probe_id,
                "library": row.get("library"),
                "model": row.get("model"),
                "parameter": row.get("parameter"),
                "expected_surface": row.get("expected_surface"),
                "expected_relation": row.get("expected_relation"),
                "outcome": row.get("outcome"),
                "pairs_total": row.get("pairs_total"),
                "pairs_eligible": row.get("pairs_eligible"),
                "pairs_matched": row.get("pairs_matched"),
                "pairs_failed": row.get("pairs_failed"),
                "matched_fraction": row.get("matched_fraction"),
                "control_aggregate": row.get("control_aggregate"),
                "treatment_aggregate": row.get("treatment_aggregate"),
            }
        )

    if seen != set(EXPECTED_PROBES):
        raise RuntimeError(f"PHASE5A_PROBE_SET_MISMATCH:{sorted(seen)}")

    checks["all_critical_checks_pass"] = all(checks.values())
    return {
        "checks": checks,
        "suite_id": suite.get("suite_id"),
        "run_id": environment.get("run_id"),
        "environment": environment,
        "manifest": manifest,
        "checksum_rows": checksum_rows,
        "results": normalized,
    }


def verify_no_source_mutation(before: dict[str, str | None]) -> dict[str, Any]:
    if source_git_output(["status", "--porcelain"]):
        raise RuntimeError("SOURCE_WORKTREE_DIRTY_AFTER_PHASE5A")
    pyproject = SOURCE_WT / "pyproject.toml"
    uv_lock = SOURCE_WT / "uv.lock"
    after = {
        "source_sha": source_git_output(["rev-parse", "HEAD"]),
        "pyproject_sha256": sha256_file(pyproject),
        "uv_lock_sha256": sha256_file(uv_lock) if uv_lock.is_file() else None,
    }
    if after != before:
        raise RuntimeError(f"SOURCE_DEPENDENCY_OR_SHA_MUTATION:before={before}:after={after}")
    return {"before": before, "after": after, "dependencies_modified": False, "lockfile_modified": False}


def local_manifest() -> None:
    manifest: list[dict[str, Any]] = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            manifest.append(
                {
                    "path": str(path.relative_to(LOCAL_OUT)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    dump_json(LOCAL_OUT / "ARTIFACT_MANIFEST.json", {"schema_version": 1, "artifacts": manifest})
    sums = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            sums.append(f"{sha256_file(path)}  {path}")
    (LOCAL_OUT / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")


def publish(summary: dict[str, Any]) -> str:
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("REFUSE_TO_PUBLISH_NON_VERIFIED_PHASE5A")
    if HANDOFF_OUT.exists():
        shutil.rmtree(HANDOFF_OUT)
    shutil.copytree(LOCAL_OUT, HANDOFF_OUT)

    report = HANDOFF_OUT / "PHASE5A_REPORT.md"
    validation = summary["validation"]
    runtime = summary["runtime"]
    report.write_text(
        "\n".join(
            [
                "# Phase 5A — existing parameter-effectiveness harness validation",
                "",
                "- status: **VERIFIED**",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                f"- selected runtime: `{runtime['candidate']}`",
                f"- Python: `{runtime.get('python')}`",
                f"- MLForecast: `{runtime.get('mlforecast')}`",
                f"- StatsForecast: `{runtime.get('statsforecast')}`",
                f"- Optuna: `{runtime.get('optuna')}`",
                "- dependency/lock mutation: **False**",
                "- Holdout evaluated: **False**",
                "- Prospective evaluated: **False**",
                "- accuracy ranking: **False**",
                "",
                "## Verified probes",
                "",
                *[
                    f"- `{row['probe_id']}`: {row['library']} / {row['model']} / "
                    f"{row['parameter']} => `{row['outcome']}` "
                    f"({row['pairs_matched']}/{row['pairs_eligible']} matched)"
                    for row in validation["results"]
                ],
                "",
                "## Interpretation",
                "",
                "Phase 5A certifies the repository-owned paired multi-seed argument-effectiveness engine using its two currently built-in real adapters. It does not certify every library or every parameter. Phase 5B must expand adapter coverage across additional Phase 4-certified runtimes before Phase 5 can be considered complete.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text("utf-8"))
    handoff["handoff_run_id"] = RUN_ID
    handoff["updated_at_utc"] = datetime.now(UTC).isoformat()
    handoff.setdefault("completed_phases", {})["phase5a"] = "VERIFIED"
    handoff["current_phase"] = "phase5a_existing_harness_verified_phase5b_adapter_expansion_next"
    handoff["phase5a"] = summary
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    progress = handoff.get("estimated_progress_percent", "unknown")
    progress_line = (
        f"- estimated progress: `{progress}%`"
        if isinstance(progress, (int, float))
        else f"- estimated progress: `{progress}`"
    )
    current = HANDOFF / "CURRENT_STATUS.md"
    current.write_text(
        "\n".join(
            [
                "# Loto Forecast Runtime Audit Handoff",
                "",
                f"Updated: {datetime.now().astimezone().isoformat()}",
                "",
                "## Current overall status",
                "",
                progress_line,
                "- Phase 4A-4H runtime ready queue: `VERIFIED / COMPLETE`",
                "- Phase 5A existing parameter-effectiveness harness: `VERIFIED`",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 5A",
                "",
                f"- runtime: `{runtime['candidate']}`",
                f"- Python: `{runtime.get('python')}`",
                f"- MLForecast: `{runtime.get('mlforecast')}`",
                f"- StatsForecast: `{runtime.get('statsforecast')}`",
                f"- Optuna: `{runtime.get('optuna')}`",
                "- MLForecast num_samples → trial_count increase: `VERIFIED`",
                "- StatsForecast season_length → prediction change: `VERIFIED`",
                "- paired seeds: `[1, 42]`",
                "- Holdout/Prospective used: `False`",
                "- dependency/lock mutation: `False`",
                "- accuracy ranking: `False`",
                "",
                "## Next",
                "",
                "Continue Phase 5B: inventory and add observable parameter-effectiveness adapters/probes for additional Phase 4-certified runtimes. Do not start Phase 6 formal ranking until Phase 5 coverage is explicitly closed or remaining gaps are classified as unsupported/inconclusive with evidence.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    file_sizes = HANDOFF / "FILE_SIZES.tsv"
    rows: list[tuple[int, Path]] = []
    for path in HANDOFF.rglob("*"):
        if path.is_file() and path != file_sizes:
            rows.append((path.stat().st_size, path))
    file_sizes.write_text(
        "".join(f"{size}\t{path}\n" for size, path in sorted(rows, reverse=True)),
        encoding="utf-8",
    )
    if any(size >= 95_000_000 for size, _ in rows):
        raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")

    sums_path = HANDOFF / "SHA256SUMS"
    lines = []
    for path in sorted(HANDOFF.rglob("*")):
        if path.is_file() and path != sums_path:
            lines.append(f"{sha256_file(path)}  {path.relative_to(HANDOFF_WT)}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    git_output(["add", "handoff"])
    check = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--check"], timeout=60)
    if check.returncode != 0:
        run(["git", "-C", str(HANDOFF_WT), "reset"], timeout=30)
        raise RuntimeError(f"STAGED_DIFF_CHECK_FAILED:{check.stdout}:{check.stderr}")

    diff = run(
        ["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--no-ext-diff", "-U0"],
        timeout=120,
    )
    added = "\n".join(
        line
        for line in diff.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    secret_pattern = re.compile(
        r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
        re.IGNORECASE,
    )
    if secret_pattern.search(added):
        run(["git", "-C", str(HANDOFF_WT), "reset"], timeout=30)
        raise RuntimeError("POTENTIAL_SECRET_IN_STAGED_DIFF")

    staged = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"], timeout=30)
    if staged.returncode == 1:
        commit = run(
            [
                "git",
                "-C",
                str(HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 5A parameter effectiveness {RUN_ID}",
            ],
            timeout=120,
        )
        if commit.returncode != 0:
            raise RuntimeError(f"HANDOFF_COMMIT_FAILED:{commit.stderr.strip()}")
    elif staged.returncode != 0:
        raise RuntimeError("STAGED_DIFF_QUERY_FAILED")

    push = run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], timeout=180)
    if push.returncode != 0:
        raise RuntimeError(f"HANDOFF_PUSH_FAILED:{push.stderr.strip()}")
    git_output(["fetch", "origin", BRANCH])
    local = git_output(["rev-parse", "HEAD"])
    remote = git_output(["rev-parse", f"origin/{BRANCH}"])
    if local != remote:
        raise RuntimeError(f"HANDOFF_REMOTE_HEAD_MISMATCH:local={local}:remote={remote}")
    if git_output(["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_DIRTY_AFTER_PUBLISH")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": "PHASE5A_PARAMETER_EFFECTIVENESS_EXISTING_ADAPTERS",
        "run_id": RUN_ID,
        "status": "FAILED",
        "source_sha": EXPECTED_SOURCE_SHA,
        "scope": "Repository-owned real-adapter parameter-effectiveness validation",
        "formal_runtime_certification": False,
        "accuracy_ranking": False,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "dependencies_modified": False,
        "lockfile_modified": False,
    }
    try:
        before = source_gate()
        handoff_sync()
        prerequisite_gate()
        if not SPEC.is_file() or not TEST_DIR.is_dir():
            raise RuntimeError("PHASE5A_SOURCE_ASSETS_MISSING")

        runtime_path, runtime, candidates = select_runtime()
        focused = run_focused_tests(runtime_path)
        suite_run = run_suite(runtime_path)
        validation = verify_evidence()
        mutation = verify_no_source_mutation(before)

        summary.update(
            {
                "status": "VERIFIED",
                "runtime": runtime,
                "runtime_candidates": candidates,
                "focused_pytest": focused,
                "suite_execution": suite_run,
                "validation": validation,
                "source_mutation_check": mutation,
                "dataset_policy": {
                    "kind": "deterministic_synthetic_development_only",
                    "holdout_evaluated": False,
                    "prospective_evaluated": False,
                    "accuracy_ranking": False,
                },
                "coverage": {
                    "built_in_adapter_libraries": ["mlforecast", "statsforecast"],
                    "verified_probe_count": 2,
                    "phase5_complete": False,
                    "reason": "Additional Phase 4-certified runtimes still require adapter/probe coverage or explicit unsupported classification.",
                },
            }
        )
        dump_json(LOCAL_OUT / "summary.json", summary)
        local_manifest()
        head = publish(summary)
        print("=" * 72)
        print("PHASE5A_PARAMETER_EFFECTIVENESS=VERIFIED")
        print(f"RUNTIME={runtime_path}")
        print("VERIFIED_PROBES=2")
        print("HOLDOUT_EVALUATED=False")
        print("PROSPECTIVE_EVALUATED=False")
        print("DEPENDENCY_MUTATION=False")
        print(f"HANDOFF_HEAD={head}")
        print(f"SUMMARY={HANDOFF_OUT / 'summary.json'}")
        print(f"REPORT={HANDOFF_OUT / 'PHASE5A_REPORT.md'}")
        print("NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 5A結果を確認してPhase 5Bへ進めてください")
        print("=" * 72)
        return 0
    except Exception as exc:
        summary["status"] = "FAILED"
        summary["error_type"] = type(exc).__name__
        summary["error"] = str(exc)
        dump_json(LOCAL_OUT / "summary.json", summary)
        local_manifest()
        print("=" * 72)
        print("PHASE5A_PARAMETER_EFFECTIVENESS=FAILED")
        print(f"ERROR={type(exc).__name__}:{exc}")
        print(f"LOCAL_SUMMARY={LOCAL_OUT / 'summary.json'}")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print("=" * 72)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
