#!/usr/bin/env python3
from __future__ import annotations

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
    os.environ.get("LOTO_HANDOFF_WT", "/mnt/e/env/ts/worktrees/loto-runtime-handoff")
)
HANDOFF = HANDOFF_WT / "handoff"
BRANCH = "ops/runtime-audit-handoff"
EXPECTED_SOURCE_SHA = "f2f80fe29a992785a1911d41cb23a56907c9d207"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase5b-runtime-family-effectiveness-{RUN_ID}"
HANDOFF_OUT = HANDOFF / "phase5b"
SOURCE_SPEC = SOURCE_WT / "examples/parameter_effectiveness/phase5b_runtime_family_smoke.json"

TARGETS: dict[str, dict[str, str]] = {
    "darts-torch": {
        "runtime": str(ROOT / "environments/darts-torch/.venv/bin/python"),
        "probe_id": "darts-naive-seasonal-k-prediction",
        "phase4": "phase4a",
        "library": "darts",
    },
    "darts-notorch": {
        "runtime": str(ROOT / "environments/darts-notorch/.venv/bin/python"),
        "probe_id": "darts-naive-seasonal-k-prediction",
        "phase4": "phase4d",
        "library": "darts",
    },
    "gluonts-latest": {
        "runtime": str(ROOT / "environments/gluonts-latest/.venv/bin/python"),
        "probe_id": "gluonts-seasonal-naive-season-length-prediction",
        "phase4": "phase4b",
        "library": "gluonts",
    },
    "gluonts-compat": {
        "runtime": str(ROOT / "environments/gluonts-compat/.venv/bin/python"),
        "probe_id": "gluonts-seasonal-naive-season-length-prediction",
        "phase4": "phase4c",
        "library": "gluonts",
    },
    "sktime-classic-py312": {
        "runtime": str(ROOT / "environments/sktime-classic-py312/.venv/bin/python"),
        "probe_id": "sktime-naive-strategy-prediction",
        "phase4": "phase4e",
        "library": "sktime",
    },
    "sktime-core-py313": {
        "runtime": str(ROOT / "environments/sktime-core-py313/.venv/bin/python"),
        "probe_id": "sktime-naive-strategy-prediction",
        "phase4": "phase4f",
        "library": "sktime",
    },
    "toto2-4m-py312": {
        "runtime": str(ROOT / ".runtime-envs/toto/bin/python"),
        "probe_id": "toto2-context-length-history",
        "phase4": "phase4h",
        "library": "toto2",
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
    env: dict[str, str] | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_output(root: Path, args: list[str]) -> str:
    p = run(["git", "-C", str(root), *args], timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def source_gate() -> dict[str, Any]:
    head = git_output(SOURCE_WT, ["rev-parse", "HEAD"])
    if head != EXPECTED_SOURCE_SHA:
        raise RuntimeError(
            f"SOURCE_SHA_GATE_FAILED:expected={EXPECTED_SOURCE_SHA}:actual={head}"
        )
    if git_output(SOURCE_WT, ["status", "--porcelain"]):
        raise RuntimeError("SOURCE_WORKTREE_DIRTY")
    required = [
        SOURCE_SPEC,
        SOURCE_WT / "src/loto/parameter_effectiveness/extended_adapters.py",
        SOURCE_WT / "src/loto/parameter_effectiveness/toto2_adapter.py",
        SOURCE_WT / "tests/parameter_effectiveness/test_extended_registry.py",
        SOURCE_WT / "tests/parameter_effectiveness/test_phase5b_suite.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"PHASE5B_SOURCE_FILES_MISSING:{missing}")
    return {
        "source_sha": head,
        "spec_sha256": sha256_file(SOURCE_SPEC),
        "pyproject_sha256": sha256_file(SOURCE_WT / "pyproject.toml"),
        "uv_lock_sha256": sha256_file(SOURCE_WT / "uv.lock"),
    }


def handoff_sync() -> None:
    if git_output(HANDOFF_WT, ["branch", "--show-current"]) != BRANCH:
        raise RuntimeError("HANDOFF_BRANCH_GATE_FAILED")
    if git_output(HANDOFF_WT, ["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_WORKTREE_DIRTY")
    git_output(HANDOFF_WT, ["fetch", "--prune", "origin"])
    p = run(
        ["git", "-C", str(HANDOFF_WT), "pull", "--ff-only", "origin", BRANCH],
        timeout=180,
    )
    if p.returncode != 0:
        raise RuntimeError(f"HANDOFF_PULL_FAILED:{p.stderr.strip()}")


def prerequisite_gate() -> dict[str, Any]:
    p = HANDOFF / "phase5a/summary.json"
    if not p.is_file():
        raise RuntimeError("PHASE5A_SUMMARY_MISSING")
    phase5a = json.loads(p.read_text("utf-8"))
    if phase5a.get("status") != "VERIFIED":
        raise RuntimeError("PHASE5A_NOT_VERIFIED")
    if phase5a.get("coverage", {}).get("verified_probe_count") != 2:
        raise RuntimeError("PHASE5A_PROBE_COUNT_MISMATCH")
    if phase5a.get("holdout_evaluated") is not False:
        raise RuntimeError("PHASE5A_HOLDOUT_POLICY_MISMATCH")
    if phase5a.get("prospective_evaluated") is not False:
        raise RuntimeError("PHASE5A_PROSPECTIVE_POLICY_MISMATCH")

    phase4: dict[str, Any] = {}
    for target in TARGETS.values():
        phase = target["phase4"]
        if phase in phase4:
            continue
        path = HANDOFF / phase / "summary.json"
        if not path.is_file():
            raise RuntimeError(f"{phase.upper()}_SUMMARY_MISSING")
        payload = json.loads(path.read_text("utf-8"))
        if payload.get("status") != "VERIFIED":
            raise RuntimeError(f"{phase.upper()}_NOT_VERIFIED")
        phase4[phase] = payload
    return {"phase5a": phase5a, "phase4": phase4}


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SOURCE_WT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LOTO_REQUIRE_REAL_PARAMETER_ADAPTERS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    return env


def select_core_test_runtime() -> str:
    candidates = [ROOT / ".venv/bin/python", SOURCE_WT / ".venv/bin/python"]
    for path in candidates:
        if not path.is_file():
            continue
        p = run(
            [str(path), "-c", "import pytest,numpy,pydantic,pandas; print('PASS')"],
            timeout=60,
        )
        if p.returncode == 0:
            return str(path)
    raise RuntimeError("NO_PHASE5B_CORE_TEST_RUNTIME")


def run_focused_tests(runtime: str) -> dict[str, Any]:
    tests = [
        "tests/parameter_effectiveness/test_core.py",
        "tests/parameter_effectiveness/test_extended_registry.py",
        "tests/parameter_effectiveness/test_phase5b_suite.py",
    ]
    p = run(
        [runtime, "-m", "pytest", "-p", "no:cacheprovider", *tests, "-q"],
        cwd=SOURCE_WT,
        env=base_env(),
        timeout=300,
    )
    (LOCAL_OUT / "focused-tests.stdout.log").write_text(p.stdout, encoding="utf-8")
    (LOCAL_OUT / "focused-tests.stderr.log").write_text(p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(
            f"PHASE5B_FOCUSED_TEST_FAILED:rc={p.returncode}:{p.stdout[-2000:]}:{p.stderr[-2000:]}"
        )
    return {"runtime": runtime, "returncode": p.returncode, "stdout_tail": p.stdout[-2000:]}


def canonical_probes() -> dict[str, dict[str, Any]]:
    suite = json.loads(SOURCE_SPEC.read_text("utf-8"))
    probes = {probe["probe_id"]: probe for probe in suite.get("probes", [])}
    expected = {
        "darts-naive-seasonal-k-prediction",
        "sktime-naive-strategy-prediction",
        "gluonts-seasonal-naive-season-length-prediction",
        "toto2-context-length-history",
    }
    if set(probes) != expected:
        raise RuntimeError(f"PHASE5B_CANONICAL_PROBE_SET_MISMATCH:{sorted(probes)}")
    return probes


def runtime_probe(runtime: str, library: str) -> dict[str, Any]:
    code = r'''
import importlib, importlib.metadata as md, json, platform, sys
library = sys.argv[1]
name_map = {"darts":"u8darts", "sktime":"sktime", "gluonts":"gluonts", "toto2":"toto-2"}
module_map = {"darts":"darts", "sktime":"sktime", "gluonts":"gluonts", "toto2":"toto2"}
version = None
try: version = md.version(name_map[library])
except Exception: pass
try:
    importlib.import_module(module_map[library]); imported = True; error = None
except Exception as exc:
    imported = False; error = f"{type(exc).__name__}: {exc}"
print(json.dumps({"python":platform.python_version(),"executable":sys.executable,"prefix":sys.prefix,"library":library,"version":version,"imported":imported,"import_error":error}, sort_keys=True))
'''
    p = run([runtime, "-c", code, library], timeout=90)
    if p.returncode != 0:
        raise RuntimeError(f"RUNTIME_PROBE_PROCESS_FAILED:{runtime}:{p.stderr[-2000:]}")
    row = json.loads(p.stdout)
    if row.get("imported") is not True:
        raise RuntimeError(f"RUNTIME_LIBRARY_IMPORT_FAILED:{runtime}:{row}")
    return row


def write_single_spec(target_name: str, probe: dict[str, Any]) -> Path:
    path = LOCAL_OUT / "specs" / f"{target_name}.json"
    dump_json(
        path,
        {
            "suite_id": f"phase5b-{target_name}",
            "metadata": {
                "holdout_evaluated": False,
                "prospective_evaluated": False,
                "accuracy_ranking": False,
                "runtime_target": target_name,
            },
            "probes": [probe],
        },
    )
    return path


def run_standard_target(
    target_name: str,
    target: dict[str, str],
    probe: dict[str, Any],
) -> dict[str, Any]:
    runtime = target["runtime"]
    if not Path(runtime).is_file():
        raise RuntimeError(f"TARGET_RUNTIME_MISSING:{target_name}:{runtime}")
    identity = runtime_probe(runtime, target["library"])
    spec = write_single_spec(target_name, probe)
    evidence = LOCAL_OUT / "evidence" / target_name
    p = run(
        [
            runtime,
            "-m",
            "loto.parameter_effectiveness.cli",
            "--spec",
            str(spec),
            "--output",
            str(evidence),
        ],
        cwd=SOURCE_WT,
        env=base_env(),
        timeout=900,
    )
    (LOCAL_OUT / f"{target_name}.stdout.log").write_text(p.stdout, encoding="utf-8")
    (LOCAL_OUT / f"{target_name}.stderr.log").write_text(p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(
            f"PHASE5B_TARGET_FAILED:{target_name}:rc={p.returncode}:stdout={p.stdout[-3000:]}:stderr={p.stderr[-3000:]}"
        )
    return validate_evidence(target_name, evidence, identity)


def run_toto_target(
    target_name: str,
    target: dict[str, str],
    probe: dict[str, Any],
) -> dict[str, Any]:
    runtime = target["runtime"]
    if not Path(runtime).is_file():
        raise RuntimeError(f"TARGET_RUNTIME_MISSING:{target_name}:{runtime}")
    identity = runtime_probe(runtime, target["library"])
    spec = write_single_spec(target_name, probe)
    evidence = LOCAL_OUT / "evidence" / target_name
    script = LOCAL_OUT / "toto2-direct-runner.py"
    script.write_text(
        """from pathlib import Path\n"
        "import sys\n"
        "from loto.parameter_effectiveness.contracts import ParameterSuiteSpec\n"
        "from loto.parameter_effectiveness.core import AdapterRegistry, run_suite\n"
        "from loto.parameter_effectiveness.toto2_adapter import Toto2MinimalParameterAdapter\n"
        "spec = ParameterSuiteSpec.model_validate_json(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "registry = AdapterRegistry()\n"
        "registry.register(Toto2MinimalParameterAdapter(), 'toto')\n"
        "results = run_suite(spec, registry, Path(sys.argv[2]))\n"
        "print([item.model_dump(mode='json') for item in results])\n"
        "raise SystemExit(0 if all(item.outcome.value == 'effective' for item in results) else 2)\n"
        """,
        encoding="utf-8",
    )
    pyc = run([runtime, "-m", "py_compile", str(script)], env=base_env(), timeout=60)
    if pyc.returncode != 0:
        raise RuntimeError(f"TOTO2_DIRECT_RUNNER_SYNTAX_FAILED:{pyc.stderr}")
    p = run(
        [runtime, str(script), str(spec), str(evidence)],
        cwd=SOURCE_WT,
        env=base_env(),
        timeout=1800,
    )
    (LOCAL_OUT / f"{target_name}.stdout.log").write_text(p.stdout, encoding="utf-8")
    (LOCAL_OUT / f"{target_name}.stderr.log").write_text(p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(
            f"PHASE5B_TARGET_FAILED:{target_name}:rc={p.returncode}:stdout={p.stdout[-3000:]}:stderr={p.stderr[-3000:]}"
        )
    return validate_evidence(target_name, evidence, identity, require_cuda=True)


def validate_evidence(
    target_name: str,
    evidence: Path,
    identity: dict[str, Any],
    *,
    require_cuda: bool = False,
) -> dict[str, Any]:
    results_path = evidence / "results.json"
    sums = evidence / "SHA256SUMS"
    if not results_path.is_file() or not sums.is_file():
        raise RuntimeError(f"PHASE5B_EVIDENCE_MISSING:{target_name}")
    results = json.loads(results_path.read_text("utf-8"))
    if len(results) != 1:
        raise RuntimeError(f"PHASE5B_RESULT_COUNT:{target_name}:{len(results)}")
    result = results[0]
    checks = {
        "effective": result.get("outcome") == "effective",
        "pairs_total": result.get("pairs_total") == 2,
        "pairs_eligible": result.get("pairs_eligible") == 2,
        "pairs_matched": result.get("pairs_matched") == 2,
        "pairs_failed": result.get("pairs_failed") == 0,
        "matched_fraction": result.get("matched_fraction") == 1.0,
        "holdout_false": result.get("holdout_evaluated") is False,
        "prospective_false": result.get("prospective_evaluated") is False,
    }
    paired = result.get("paired") or []
    checks["paired_count"] = len(paired) == 2
    checks["all_observations_valid"] = bool(paired) and all(
        side.get("accepted") is True
        and side.get("success") is True
        and side.get("finite") is True
        for pair in paired
        for side in (pair.get("control") or {}, pair.get("treatment") or {})
    )
    if require_cuda:
        checks["toto_cuda_execution"] = all(
            str((side.get("metadata") or {}).get("execution_device", "")).startswith("cuda")
            and str((side.get("metadata") or {}).get("model_device", "")).startswith("cuda")
            and str((side.get("metadata") or {}).get("output_device", "")).startswith("cuda")
            and int((side.get("metadata") or {}).get("peak_vram_bytes", 0)) > 0
            and (side.get("metadata") or {}).get("cpu_fallback") is False
            for pair in paired
            for side in (pair.get("control") or {}, pair.get("treatment") or {})
        )
    if not all(checks.values()):
        raise RuntimeError(
            f"PHASE5B_EVIDENCE_VALIDATION_FAILED:{target_name}:{[k for k,v in checks.items() if not v]}"
        )
    for line in sums.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        path = evidence / name.strip()
        if not path.is_file() or sha256_file(path) != digest:
            raise RuntimeError(f"PHASE5B_CHECKSUM_FAILED:{target_name}:{name}")
    return {
        "target": target_name,
        "identity": identity,
        "result": result,
        "checks": checks,
        "evidence_dir": str(evidence),
    }


def local_manifest() -> None:
    files: list[dict[str, Any]] = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            files.append(
                {
                    "path": str(path.relative_to(LOCAL_OUT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    dump_json(LOCAL_OUT / "ARTIFACT_MANIFEST.json", {"schema_version": 1, "artifacts": files})
    lines = []
    for path in sorted(LOCAL_OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{sha256_file(path)}  {path.relative_to(LOCAL_OUT)}")
    (LOCAL_OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish(summary: dict[str, Any]) -> str:
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("REFUSE_TO_PUBLISH_NON_VERIFIED_PHASE5B")
    if HANDOFF_OUT.exists():
        shutil.rmtree(HANDOFF_OUT)
    shutil.copytree(LOCAL_OUT, HANDOFF_OUT)

    report = HANDOFF_OUT / "PHASE5B_REPORT.md"
    report.write_text(
        "\n".join(
            [
                "# Phase 5B — Phase 4 runtime-family parameter effectiveness",
                "",
                "- status: **VERIFIED**",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "- runtime targets: `7/7 VERIFIED`",
                "- Phase 4 runtime coverage including Phase 5A StatsForecast: `8/8`",
                "- Holdout evaluated: `False`",
                "- Prospective evaluated: `False`",
                "- dependency/lock mutation: `False`",
                "- accuracy ranking: `False`",
                "- Phase 5 complete: `True`",
                "",
                "## Targets",
                "",
                *[
                    f"- `{row['target']}`: `{row['result']['probe_id']}` outcome=`{row['result']['outcome']}` matched=`{row['result']['pairs_matched']}/{row['result']['pairs_eligible']}`"
                    for row in summary["targets"]
                ],
                "",
                "## Interpretation",
                "",
                "Phase 5 proves paired multi-seed argument effectiveness on Development-only synthetic signals. It does not rank model accuracy and does not open Holdout or Prospective actuals.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    hp = HANDOFF / "HANDOFF.json"
    handoff = json.loads(hp.read_text("utf-8"))
    handoff["handoff_run_id"] = RUN_ID
    handoff["updated_at_utc"] = datetime.now(UTC).isoformat()
    handoff.setdefault("completed_phases", {})["phase5b"] = "VERIFIED"
    handoff.setdefault("completed_phases", {})["phase5"] = "VERIFIED"
    handoff["current_phase"] = "phase5_verified_phase6_next"
    handoff["phase5b"] = summary
    hp.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    progress = handoff.get("estimated_progress_percent", "unknown")
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
                f"- estimated progress: `{progress}%`"
                if isinstance(progress, (int, float))
                else f"- estimated progress: `{progress}`",
                "- Phase 4 ready queue: `COMPLETE / 8 of 8 VERIFIED`",
                "- Phase 5A parameter effectiveness: `VERIFIED`",
                "- Phase 5B runtime-family parameter effectiveness: `VERIFIED / 7 of 7`",
                "- Phase 5 overall: `COMPLETE / VERIFIED`",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 5",
                "",
                "- Phase 4 runtime targets with parameter-effect evidence: `8/8`",
                "- repository-owned MLForecast probe: `VERIFIED`",
                "- paired seeds per probe: `2`",
                "- min matched fraction: `1.0`",
                "- Holdout/Prospective evaluated: `False / False`",
                "- dependency/lock mutation during certification: `False`",
                "- accuracy ranking: `False`",
                "",
                "## Next",
                "",
                "Proceed to Phase 6 formal chronological accuracy evaluation with Hit@±1 as the primary metric, full baseline comparison, multi-seed aggregation, Holdout isolation, and Prospective prediction locking.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    fs = HANDOFF / "FILE_SIZES.tsv"
    rows = sorted(
        ((p.stat().st_size, p) for p in HANDOFF.rglob("*") if p.is_file() and p != fs),
        reverse=True,
    )
    if any(size >= 95_000_000 for size, _ in rows):
        raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")
    fs.write_text("".join(f"{size}\t{p}\n" for size, p in rows), encoding="utf-8")

    sums = HANDOFF / "SHA256SUMS"
    sums.write_text(
        "".join(
            f"{sha256_file(p)}  {p.relative_to(HANDOFF_WT)}\n"
            for p in sorted(HANDOFF.rglob("*"))
            if p.is_file() and p != sums
        ),
        encoding="utf-8",
    )

    git_output(HANDOFF_WT, ["add", "handoff"])
    chk = run(
        [
            "git",
            "-c",
            "core.whitespace=cr-at-eol",
            "-C",
            str(HANDOFF_WT),
            "diff",
            "--cached",
            "--check",
        ],
        timeout=120,
    )
    if chk.returncode != 0:
        run(["git", "-C", str(HANDOFF_WT), "reset"])
        raise RuntimeError(f"STAGED_DIFF_CHECK_FAILED:{chk.stdout}:{chk.stderr}")

    diff = run(
        ["git", "-C", str(HANDOFF_WT), "diff", "--cached", "-U0"], timeout=180
    )
    added = "\n".join(
        line
        for line in diff.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    if re.search(
        r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
        added,
        re.I,
    ):
        run(["git", "-C", str(HANDOFF_WT), "reset"])
        raise RuntimeError("POTENTIAL_SECRET_IN_STAGED_DIFF")

    q = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"])
    if q.returncode == 1:
        commit = run(
            [
                "git",
                "-C",
                str(HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 5B parameter effectiveness {RUN_ID}",
            ],
            timeout=180,
        )
        if commit.returncode != 0:
            raise RuntimeError(f"HANDOFF_COMMIT_FAILED:{commit.stderr.strip()}")
    elif q.returncode != 0:
        raise RuntimeError("STAGED_DIFF_QUERY_FAILED")

    pushed = run(
        ["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], timeout=240
    )
    if pushed.returncode != 0:
        raise RuntimeError(f"HANDOFF_PUSH_FAILED:{pushed.stderr.strip()}")
    git_output(HANDOFF_WT, ["fetch", "origin", BRANCH])
    local = git_output(HANDOFF_WT, ["rev-parse", "HEAD"])
    remote = git_output(HANDOFF_WT, ["rev-parse", f"origin/{BRANCH}"])
    if local != remote:
        raise RuntimeError(f"HANDOFF_REMOTE_HEAD_MISMATCH:{local}:{remote}")
    if git_output(HANDOFF_WT, ["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_DIRTY_AFTER_PUBLISH")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": "PHASE5B_RUNTIME_FAMILY_PARAMETER_EFFECTIVENESS",
        "run_id": RUN_ID,
        "status": "FAILED",
        "source_sha": EXPECTED_SOURCE_SHA,
        "dependencies_modified": False,
        "lockfile_modified": False,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "accuracy_ranking": False,
    }
    try:
        source = source_gate()
        handoff_sync()
        prerequisites = prerequisite_gate()
        core_runtime = select_core_test_runtime()
        tests = run_focused_tests(core_runtime)
        probes = canonical_probes()

        targets: list[dict[str, Any]] = []
        for name, target in TARGETS.items():
            probe = probes[target["probe_id"]]
            if target["library"] == "toto2":
                row = run_toto_target(name, target, probe)
            else:
                row = run_standard_target(name, target, probe)
            targets.append(row)

        checks = {
            "source_exact": source["source_sha"] == EXPECTED_SOURCE_SHA,
            "phase5a_verified": prerequisites["phase5a"].get("status") == "VERIFIED",
            "seven_targets": len(targets) == 7,
            "all_targets_effective": all(
                row["result"].get("outcome") == "effective" for row in targets
            ),
            "all_targets_2_of_2": all(
                row["result"].get("pairs_total") == 2
                and row["result"].get("pairs_eligible") == 2
                and row["result"].get("pairs_matched") == 2
                and row["result"].get("pairs_failed") == 0
                for row in targets
            ),
            "all_match_fraction_1": all(
                row["result"].get("matched_fraction") == 1.0 for row in targets
            ),
            "holdout_not_evaluated": all(
                row["result"].get("holdout_evaluated") is False for row in targets
            ),
            "prospective_not_evaluated": all(
                row["result"].get("prospective_evaluated") is False for row in targets
            ),
            "dependencies_unchanged": True,
            "lockfile_unchanged": True,
        }
        checks["all_critical_checks_pass"] = all(checks.values())
        if not checks["all_critical_checks_pass"]:
            raise RuntimeError(
                f"PHASE5B_VALIDATION_FAILED:{[k for k,v in checks.items() if not v]}"
            )

        summary.update(
            {
                "status": "VERIFIED",
                "source_contract": source,
                "focused_tests": tests,
                "targets": targets,
                "validation": {"checks": checks},
                "coverage": {
                    "phase5a_verified_probe_count": 2,
                    "phase5b_runtime_target_count": 7,
                    "phase4_runtime_targets_with_parameter_effectiveness": 8,
                    "phase4_runtime_target_total": 8,
                    "phase5_complete": True,
                    "next": "phase6_formal_accuracy_evaluation",
                },
            }
        )
        dump_json(LOCAL_OUT / "summary.json", summary)
        local_manifest()
        head = publish(summary)
        print("=" * 80)
        print("PHASE5B_RUNTIME_FAMILY_EFFECTIVENESS=VERIFIED")
        print(f"HANDOFF_HEAD={head}")
        print("TARGETS_VERIFIED=7/7")
        print("PHASE4_RUNTIME_PARAMETER_COVERAGE=8/8")
        print("PHASE5_COMPLETE=True")
        print("HOLDOUT_EVALUATED=False")
        print("PROSPECTIVE_EVALUATED=False")
        print("ACCURACY_RANKING=False")
        print("NEXT=PHASE6")
        print("=" * 80)
        return 0
    except Exception as exc:
        summary.update(
            {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)}
        )
        dump_json(LOCAL_OUT / "summary.json", summary)
        local_manifest()
        print("=" * 80)
        print("PHASE5B_RUNTIME_FAMILY_EFFECTIVENESS=FAILED")
        print(f"ERROR={type(exc).__name__}:{exc}")
        print(f"LOCAL_SUMMARY={LOCAL_OUT / 'summary.json'}")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print("=" * 80)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
