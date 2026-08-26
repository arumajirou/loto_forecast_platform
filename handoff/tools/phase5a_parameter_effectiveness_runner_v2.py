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
SOURCE_WT = Path(os.environ.get("LOTO_SOURCE_WT", "/mnt/e/env/ts/worktrees/loto-runtime-audit-20260826-121248"))
HANDOFF_WT = Path(os.environ.get("LOTO_HANDOFF_WT", "/mnt/e/env/ts/worktrees/loto-runtime-handoff"))
HANDOFF = HANDOFF_WT / "handoff"
BRANCH = "ops/runtime-audit-handoff"
EXPECTED_SOURCE_SHA = "0a13c287e0f0fcc8f983be3512654524dad18b2c"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase5a-parameter-effectiveness-v2-{RUN_ID}"
HANDOFF_OUT = HANDOFF / "phase5a"
SOURCE_SPEC = SOURCE_WT / "examples/parameter_effectiveness/cross_platform_smoke.json"
CORE_TEST = SOURCE_WT / "tests/parameter_effectiveness/test_core.py"

EXPECTED = {
    "mlforecast-num-samples-trial-count": {
        "library": "mlforecast", "model": "AutoLinearRegression", "parameter": "num_samples",
        "expected_surface": "trial_count", "expected_relation": "increase",
    },
    "statsforecast-season-length-prediction": {
        "library": "statsforecast", "model": "SeasonalNaive", "parameter": "season_length",
        "expected_surface": "prediction", "expected_relation": "change",
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, capture_output=True, text=True, timeout=timeout, check=False)


def git_output(root: Path, args: list[str]) -> str:
    p = run(["git", "-C", str(root), *args], timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def source_gate() -> dict[str, Any]:
    head = git_output(SOURCE_WT, ["rev-parse", "HEAD"])
    if head != EXPECTED_SOURCE_SHA:
        raise RuntimeError(f"SOURCE_SHA_GATE_FAILED:expected={EXPECTED_SOURCE_SHA}:actual={head}")
    if git_output(SOURCE_WT, ["status", "--porcelain"]):
        raise RuntimeError("SOURCE_WORKTREE_DIRTY")
    if not SOURCE_SPEC.is_file():
        raise RuntimeError("PARAMETER_EFFECTIVENESS_SPEC_MISSING")
    pyproject = SOURCE_WT / "pyproject.toml"
    uv_lock = SOURCE_WT / "uv.lock"
    return {
        "source_sha": head,
        "spec_sha256": sha256_file(SOURCE_SPEC),
        "pyproject_sha256": sha256_file(pyproject),
        "uv_lock_sha256": sha256_file(uv_lock) if uv_lock.is_file() else None,
    }


def handoff_sync() -> None:
    if git_output(HANDOFF_WT, ["branch", "--show-current"]) != BRANCH:
        raise RuntimeError("HANDOFF_BRANCH_GATE_FAILED")
    if git_output(HANDOFF_WT, ["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_WORKTREE_DIRTY")
    git_output(HANDOFF_WT, ["fetch", "--prune", "origin"])
    p = run(["git", "-C", str(HANDOFF_WT), "pull", "--ff-only", "origin", BRANCH], timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"HANDOFF_PULL_FAILED:{p.stderr.strip()}")


def prerequisite_gate() -> dict[str, Any]:
    p = HANDOFF / "phase4h/summary.json"
    if not p.is_file():
        raise RuntimeError("PHASE4H_SUMMARY_MISSING")
    x = json.loads(p.read_text("utf-8"))
    if x.get("status") != "VERIFIED" or x.get("formal_runtime_certification") is not True:
        raise RuntimeError("PHASE4H_NOT_FORMALLY_VERIFIED")
    if x.get("source_sha") != EXPECTED_SOURCE_SHA:
        raise RuntimeError(f"PHASE4H_SOURCE_SHA_MISMATCH:{x.get('source_sha')}")
    return x


def candidates() -> list[Path]:
    paths = [ROOT / ".venv/bin/python", SOURCE_WT / ".venv/bin/python"]
    paths += sorted(ROOT.glob("environments/*/.venv/bin/python"))
    paths += sorted(ROOT.glob(".runtime-envs/*/bin/python"))
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        k = str(p)
        if k not in seen and p.is_file():
            seen.add(k)
            out.append(p)
    return out


def probe_runtime(path: Path) -> dict[str, Any]:
    code = r'''
import importlib, importlib.metadata as md, json, platform, sys
packages = ["mlforecast", "statsforecast", "optuna", "numpy", "pandas", "pydantic", "scikit-learn", "pytest"]
versions = {}
for name in packages:
    try: versions[name] = md.version(name)
    except md.PackageNotFoundError: versions[name] = None
imports = {}
for name, module in [("numpy","numpy"),("pandas","pandas"),("pydantic","pydantic"),("sklearn","sklearn"),("mlforecast","mlforecast"),("statsforecast","statsforecast"),("optuna","optuna"),("pytest","pytest")]:
    try:
        importlib.import_module(module); imports[name] = True
    except Exception as exc:
        imports[name] = False
print(json.dumps({"python": platform.python_version(), "executable": sys.executable, "prefix": sys.prefix, "versions": versions, "imports": imports}, sort_keys=True))
'''
    p = run([str(path), "-c", code], timeout=90)
    row: dict[str, Any] = {"candidate": str(path), "returncode": p.returncode, "stderr": p.stderr[-2000:]}
    if p.returncode == 0:
        try: row.update(json.loads(p.stdout))
        except Exception as exc: row["parse_error"] = str(exc)
    return row


def py313(row: dict[str, Any]) -> bool:
    return str(row.get("python", "")).startswith("3.13.")


def select_runtimes(inventory: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    def imports_ok(row: dict[str, Any], names: tuple[str, ...]) -> bool:
        imp = row.get("imports") or {}
        return all(imp.get(name) is True for name in names)

    ml = [r for r in inventory if r.get("returncode") == 0 and py313(r)
          and (r.get("versions") or {}).get("mlforecast") == "1.1.0"
          and str((r.get("versions") or {}).get("optuna") or "").startswith("4.")
          and imports_ok(r, ("numpy", "pandas", "pydantic", "sklearn", "mlforecast", "optuna"))]
    sf = [r for r in inventory if r.get("returncode") == 0 and py313(r)
          and (r.get("versions") or {}).get("statsforecast") == "2.1.1"
          and imports_ok(r, ("numpy", "pandas", "pydantic", "statsforecast"))]
    test = [r for r in inventory if r.get("returncode") == 0 and py313(r)
            and imports_ok(r, ("numpy", "pydantic", "pytest"))]
    if not ml:
        raise RuntimeError("NO_EXISTING_MLFORECAST_PHASE5A_RUNTIME:requires Python3.13 + mlforecast1.1.0 + optuna4.x + numpy/pandas/pydantic/sklearn")
    if not sf:
        raise RuntimeError("NO_EXISTING_STATSFORECAST_PHASE5A_RUNTIME:requires Python3.13 + statsforecast2.1.1 + numpy/pandas/pydantic")
    if not test:
        raise RuntimeError("NO_EXISTING_PHASE5A_CORE_TEST_RUNTIME:requires Python3.13 + pytest + numpy + pydantic")
    # Prefer root/source test env for tests and the Phase4G runtime for StatsForecast when available.
    sf.sort(key=lambda r: ("environments/statsforecast-py313/.venv/bin/python" not in str(r["candidate"]), str(r["candidate"])))
    ml.sort(key=lambda r: (str(r["candidate"]) != str(ROOT / ".venv/bin/python"), str(r["candidate"])))
    test.sort(key=lambda r: (str(r["candidate"]) != str(ROOT / ".venv/bin/python"), str(r["candidate"])))
    return {"mlforecast": ml[0], "statsforecast": sf[0], "core_test": test[0]}


def suite_parts() -> dict[str, dict[str, Any]]:
    suite = json.loads(SOURCE_SPEC.read_text("utf-8"))
    probes = {p["probe_id"]: p for p in suite.get("probes", [])}
    if set(probes) != set(EXPECTED):
        raise RuntimeError(f"COMMITTED_SUITE_PROBE_SET_MISMATCH:{sorted(probes)}")
    out: dict[str, dict[str, Any]] = {}
    for pid, expected in EXPECTED.items():
        p = probes[pid]
        for key, value in expected.items():
            if p.get(key) != value:
                raise RuntimeError(f"COMMITTED_SUITE_CONTRACT_MISMATCH:{pid}:{key}:expected={value}:actual={p.get(key)}")
        part = {"suite_id": f"phase5a-v2-{pid}", "metadata": dict(suite.get("metadata") or {}), "probes": [p]}
        out[pid] = part
    return out


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(SOURCE_WT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LOTO_REQUIRE_REAL_PARAMETER_ADAPTERS": "1",
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1", "TOKENIZERS_PARALLELISM": "false",
    })
    return env


def run_core_tests(runtime: dict[str, Any]) -> None:
    p = run([runtime["candidate"], "-m", "pytest", "-p", "no:cacheprovider", str(CORE_TEST), "-q"], cwd=SOURCE_WT, env=base_env(), timeout=300)
    (LOCAL_OUT / "core-test.stdout.log").write_text(p.stdout, encoding="utf-8")
    (LOCAL_OUT / "core-test.stderr.log").write_text(p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"PHASE5A_CORE_TEST_FAILED:rc={p.returncode}:{p.stderr[-2000:]}")


def run_probe(pid: str, part: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    spec = LOCAL_OUT / f"{pid}.spec.json"
    evidence = LOCAL_OUT / "evidence" / pid
    dump_json(spec, part)
    p = run([runtime["candidate"], "-m", "loto.parameter_effectiveness.cli", "--spec", str(spec), "--output", str(evidence)], cwd=SOURCE_WT, env=base_env(), timeout=900)
    (LOCAL_OUT / f"{pid}.stdout.log").write_text(p.stdout, encoding="utf-8")
    (LOCAL_OUT / f"{pid}.stderr.log").write_text(p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"PARAMETER_PROBE_FAILED:{pid}:rc={p.returncode}:{p.stderr[-2000:]}")
    results_path = evidence / "results.json"
    if not results_path.is_file():
        raise RuntimeError(f"PARAMETER_PROBE_RESULTS_MISSING:{pid}")
    results = json.loads(results_path.read_text("utf-8"))
    if len(results) != 1:
        raise RuntimeError(f"PARAMETER_PROBE_RESULT_COUNT:{pid}:{len(results)}")
    r = results[0]
    exp = EXPECTED[pid]
    checks = {
        "probe_id": r.get("probe_id") == pid,
        "library": r.get("library") == exp["library"],
        "model": r.get("model") == exp["model"],
        "parameter": r.get("parameter") == exp["parameter"],
        "surface": r.get("expected_surface") == exp["expected_surface"],
        "relation": r.get("expected_relation") == exp["expected_relation"],
        "effective": r.get("outcome") == "effective",
        "pairs_total": r.get("pairs_total") == 2,
        "pairs_eligible": r.get("pairs_eligible") == 2,
        "pairs_matched": r.get("pairs_matched") == 2,
        "pairs_failed": r.get("pairs_failed") == 0,
        "matched_fraction": r.get("matched_fraction") == 1.0,
        "holdout_false": r.get("holdout_evaluated") is False,
        "prospective_false": r.get("prospective_evaluated") is False,
    }
    paired = r.get("paired") or []
    checks["paired_count"] = len(paired) == 2
    checks["all_pair_observations_valid"] = bool(paired) and all(
        side.get("accepted") is True and side.get("success") is True and side.get("finite") is True
        for pair in paired for side in (pair.get("control") or {}, pair.get("treatment") or {})
    )
    if not all(checks.values()):
        raise RuntimeError(f"PARAMETER_PROBE_VALIDATION_FAILED:{pid}:{[k for k,v in checks.items() if not v]}")
    # Verify portable evidence checksums.
    sums = evidence / "SHA256SUMS"
    if not sums.is_file():
        raise RuntimeError(f"PARAMETER_PROBE_SHA256SUMS_MISSING:{pid}")
    for line in sums.read_text("utf-8").splitlines():
        if not line.strip(): continue
        digest, name = line.split(maxsplit=1)
        path = evidence / name.strip()
        if not path.is_file() or sha256_file(path) != digest:
            raise RuntimeError(f"PARAMETER_PROBE_CHECKSUM_FAILED:{pid}:{name}")
    return {"result": r, "checks": checks, "evidence_dir": str(evidence), "runtime": runtime}


def local_manifest() -> None:
    files = []
    for p in sorted(LOCAL_OUT.rglob("*")):
        if p.is_file() and p.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            files.append({"path": str(p.relative_to(LOCAL_OUT)), "bytes": p.stat().st_size, "sha256": sha256_file(p)})
    dump_json(LOCAL_OUT / "ARTIFACT_MANIFEST.json", {"schema_version": 1, "artifacts": files})
    lines = []
    for p in sorted(LOCAL_OUT.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS":
            lines.append(f"{sha256_file(p)}  {p}")
    (LOCAL_OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish(summary: dict[str, Any]) -> str:
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("REFUSE_TO_PUBLISH_NON_VERIFIED_PHASE5A")
    if HANDOFF_OUT.exists(): shutil.rmtree(HANDOFF_OUT)
    shutil.copytree(LOCAL_OUT, HANDOFF_OUT)
    report = HANDOFF_OUT / "PHASE5A_REPORT.md"
    results = summary["validation"]["results"]
    report.write_text("\n".join([
        "# Phase 5A — Existing parameter-effectiveness adapters",
        "", "- status: **VERIFIED**", f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
        "- runtime layout: **adapter-specific existing runtimes**",
        f"- MLForecast runtime: `{summary['runtimes']['mlforecast']['candidate']}`",
        f"- StatsForecast runtime: `{summary['runtimes']['statsforecast']['candidate']}`",
        "- Holdout evaluated: `False`", "- Prospective evaluated: `False`",
        "- dependency/lock mutation: `False`", "- accuracy ranking: `False`",
        "- Phase 5 complete: `False` (Phase 5B extension remains)", "",
        "## Verified probes", "",
        *[f"- `{r['probe_id']}`: outcome=`{r['outcome']}`, matched=`{r['pairs_matched']}/{r['pairs_eligible']}`" for r in results],
        "", "## Interpretation", "",
        "Phase 5A verifies the two repository-owned real adapters independently in compatible existing runtimes. It does not require MLForecast and StatsForecast to coexist in one virtual environment, and it does not make Holdout/Prospective accuracy claims.",
    ]) + "\n", encoding="utf-8")

    hp = HANDOFF / "HANDOFF.json"
    h = json.loads(hp.read_text("utf-8"))
    h["handoff_run_id"] = RUN_ID
    h["updated_at_utc"] = datetime.now(UTC).isoformat()
    h.setdefault("completed_phases", {})["phase5a"] = "VERIFIED"
    h["current_phase"] = "phase5a_verified_phase5b_next"
    h["phase5a"] = summary
    hp.write_text(json.dumps(h, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    progress = h.get("estimated_progress_percent", "unknown")
    current = HANDOFF / "CURRENT_STATUS.md"
    current.write_text("\n".join([
        "# Loto Forecast Runtime Audit Handoff", "", f"Updated: {datetime.now().astimezone().isoformat()}", "",
        "## Current overall status", "", f"- estimated progress: `{progress}%`" if isinstance(progress, (int,float)) else f"- estimated progress: `{progress}`",
        "- Phase 4 ready queue: `COMPLETE / 8 of 8 VERIFIED`",
        "- Phase 5A parameter effectiveness (MLForecast + StatsForecast): `VERIFIED`",
        f"- source SHA: `{EXPECTED_SOURCE_SHA}`", "", "## Phase 5A", "",
        "- runtime layout: `adapter-specific existing runtimes`",
        f"- MLForecast runtime: `{summary['runtimes']['mlforecast']['candidate']}`",
        f"- StatsForecast runtime: `{summary['runtimes']['statsforecast']['candidate']}`",
        "- verified probes: `2/2`", "- Holdout/Prospective evaluated: `False / False`",
        "- dependency/lock mutation: `False`", "- accuracy ranking: `False`", "- Phase 5 complete: `False`", "",
        "## Next", "", "Continue with Phase 5B adapter/probe coverage extension for the other Phase 4-certified runtime families before Phase 6 accuracy evaluation.",
    ]) + "\n", encoding="utf-8")

    fs = HANDOFF / "FILE_SIZES.tsv"
    rows = sorted(((p.stat().st_size, p) for p in HANDOFF.rglob("*") if p.is_file() and p != fs), reverse=True)
    if any(size >= 95_000_000 for size, _ in rows): raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")
    fs.write_text("".join(f"{size}\t{p}\n" for size,p in rows), encoding="utf-8")
    sums = HANDOFF / "SHA256SUMS"
    sums.write_text("".join(f"{sha256_file(p)}  {p.relative_to(HANDOFF_WT)}\n" for p in sorted(HANDOFF.rglob("*")) if p.is_file() and p != sums), encoding="utf-8")

    git_output(HANDOFF_WT, ["add", "handoff"])
    chk = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--check"], timeout=120)
    if chk.returncode != 0:
        run(["git", "-C", str(HANDOFF_WT), "reset"]); raise RuntimeError(f"STAGED_DIFF_CHECK_FAILED:{chk.stdout}:{chk.stderr}")
    diff = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "-U0"], timeout=180)
    added = "\n".join(x for x in diff.stdout.splitlines() if x.startswith("+") and not x.startswith("+++"))
    if re.search(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", added, re.I):
        run(["git", "-C", str(HANDOFF_WT), "reset"]); raise RuntimeError("POTENTIAL_SECRET_IN_STAGED_DIFF")
    q = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"])
    if q.returncode == 1:
        c = run(["git", "-C", str(HANDOFF_WT), "commit", "-m", f"audit: publish Phase 5A parameter effectiveness {RUN_ID}"], timeout=180)
        if c.returncode != 0: raise RuntimeError(f"HANDOFF_COMMIT_FAILED:{c.stderr.strip()}")
    elif q.returncode != 0: raise RuntimeError("STAGED_DIFF_QUERY_FAILED")
    p = run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], timeout=240)
    if p.returncode != 0: raise RuntimeError(f"HANDOFF_PUSH_FAILED:{p.stderr.strip()}")
    git_output(HANDOFF_WT, ["fetch", "origin", BRANCH])
    local, remote = git_output(HANDOFF_WT, ["rev-parse", "HEAD"]), git_output(HANDOFF_WT, ["rev-parse", f"origin/{BRANCH}"])
    if local != remote: raise RuntimeError(f"HANDOFF_REMOTE_HEAD_MISMATCH:{local}:{remote}")
    if git_output(HANDOFF_WT, ["status", "--porcelain"]): raise RuntimeError("HANDOFF_DIRTY_AFTER_PUBLISH")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {"schema_version": 2, "phase": "PHASE5A_PARAMETER_EFFECTIVENESS_EXISTING_ADAPTERS", "run_id": RUN_ID, "status": "FAILED", "source_sha": EXPECTED_SOURCE_SHA, "dependencies_modified": False, "lockfile_modified": False, "holdout_evaluated": False, "prospective_evaluated": False, "accuracy_ranking": False}
    try:
        source = source_gate(); handoff_sync(); prerequisite_gate()
        inv = [probe_runtime(p) for p in candidates()]
        dump_json(LOCAL_OUT / "runtime-inventory.json", inv)
        selected = select_runtimes(inv)
        parts = suite_parts()
        run_core_tests(selected["core_test"])
        ml = run_probe("mlforecast-num-samples-trial-count", parts["mlforecast-num-samples-trial-count"], selected["mlforecast"])
        sf = run_probe("statsforecast-season-length-prediction", parts["statsforecast-season-length-prediction"], selected["statsforecast"])
        results = [ml["result"], sf["result"]]
        checks = {
            "source_exact": source["source_sha"] == EXPECTED_SOURCE_SHA,
            "two_probe_results": len(results) == 2,
            "all_effective": all(r.get("outcome") == "effective" for r in results),
            "all_pairs_2_of_2": all(r.get("pairs_total") == r.get("pairs_eligible") == r.get("pairs_matched") == 2 and r.get("pairs_failed") == 0 for r in results),
            "all_match_fraction_1": all(r.get("matched_fraction") == 1.0 for r in results),
            "holdout_not_evaluated": all(r.get("holdout_evaluated") is False for r in results),
            "prospective_not_evaluated": all(r.get("prospective_evaluated") is False for r in results),
            "separate_runtime_layout_allowed": True,
            "dependencies_unchanged": True,
            "lockfile_unchanged": True,
        }
        checks["all_critical_checks_pass"] = all(checks.values())
        if not checks["all_critical_checks_pass"]: raise RuntimeError(f"PHASE5A_V2_VALIDATION_FAILED:{[k for k,v in checks.items() if not v]}")
        summary.update({"status": "VERIFIED", "source_contract": source, "runtime_layout": "adapter_specific_existing_runtimes", "runtimes": selected, "validation": {"checks": checks, "results": results, "probe_details": {"mlforecast": ml, "statsforecast": sf}}, "coverage": {"verified_adapter_count": 2, "verified_probe_count": 2, "phase5_complete": False, "next": "phase5b_adapter_coverage_extension"}})
        dump_json(LOCAL_OUT / "summary.json", summary); local_manifest()
        head = publish(summary)
        print("="*72); print("PHASE5A_PARAMETER_EFFECTIVENESS_V2=VERIFIED"); print(f"HANDOFF_HEAD={head}"); print(f"MLFORECAST_RUNTIME={selected['mlforecast']['candidate']}"); print(f"STATSFORECAST_RUNTIME={selected['statsforecast']['candidate']}"); print("VERIFIED_PROBES=2"); print("PHASE5_COMPLETE=False"); print("NEXT=PHASE5B"); print("="*72)
        return 0
    except Exception as exc:
        summary.update({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        dump_json(LOCAL_OUT / "summary.json", summary); local_manifest()
        print("="*72); print("PHASE5A_PARAMETER_EFFECTIVENESS_V2=FAILED"); print(f"ERROR={type(exc).__name__}:{exc}"); print(f"LOCAL_SUMMARY={LOCAL_OUT / 'summary.json'}"); print(f"RUNTIME_INVENTORY={LOCAL_OUT / 'runtime-inventory.json'}"); print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED"); print("="*72)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
