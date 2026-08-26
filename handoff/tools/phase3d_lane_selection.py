#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
except Exception as exc:
    raise SystemExit(f"packaging is required for Phase 3D: {exc}")

REPO = Path(os.environ.get("LOTO_ROOT", "/mnt/e/env/ts/loto_forecast_platform"))
SOURCE_WT = Path(os.environ.get("LOTO_SOURCE_WT", "/mnt/e/env/ts/worktrees/loto-runtime-audit-20260826-121248"))
HANDOFF_WT = Path(os.environ.get("LOTO_HANDOFF_WT", "/mnt/e/env/ts/worktrees/loto-runtime-handoff"))
BRANCH = "ops/runtime-audit-handoff"
EXPECTED_SOURCE_SHA = "8af95b2be18280589cbbb13aa1fc32dfb793767c"
HANDOFF = HANDOFF_WT / "handoff"
PHASE3B = HANDOFF / "phase3b"
PHASE3C = HANDOFF / "phase3c"
OUT = HANDOFF / "phase3d"


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for row in rows:
            out: dict[str, Any] = {}
            for field in fields:
                value = row.get(field, "")
                if isinstance(value, (list, dict, tuple, set)):
                    if isinstance(value, set):
                        value = sorted(value)
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                out[field] = value
            w.writerow(out)


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n", encoding="utf-8")


def parse_json_cell(value: str) -> Any:
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return [value]


def package_probe(prefix: str) -> dict[str, Any]:
    python = Path(prefix) / "bin/python"
    if not python.exists():
        return {"status": "PYTHON_MISSING", "python": str(python), "packages": {}}
    code = r'''
import importlib.metadata, json, platform, sys
pkgs = {}
for dist in importlib.metadata.distributions():
    try:
        name = (dist.metadata.get("Name") or "").strip().lower()
        if name:
            pkgs[name] = str(dist.version)
    except Exception:
        pass
print("__LANE__" + json.dumps({"python_version": platform.python_version(), "packages": pkgs, "sys_prefix": sys.prefix}, sort_keys=True))
'''
    try:
        p = subprocess.run([str(python), "-I", "-c", code], text=True, capture_output=True, timeout=45)
    except Exception as exc:
        return {"status": "PROBE_FAILED", "python": str(python), "error": f"{type(exc).__name__}: {exc}", "packages": {}}
    marker = "__LANE__"
    for line in reversed(p.stdout.splitlines()):
        if line.startswith(marker):
            payload = json.loads(line[len(marker):])
            payload["status"] = "PASS" if p.returncode == 0 else "PROCESS_FAILED"
            payload["python"] = str(python)
            return payload
    return {"status": "INVALID_OUTPUT", "python": str(python), "packages": {}, "stderr": p.stderr[-2000:]}


def source_contract(environment: str) -> dict[str, Any]:
    pp = SOURCE_WT / environment / "pyproject.toml"
    data = tomllib.loads(pp.read_text(encoding="utf-8"))
    project = data.get("project", {})
    return {
        "requires_python": project.get("requires-python", ""),
        "dependencies": list(project.get("dependencies", [])),
    }


def compare_contract(contract: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    if probe.get("status") != "PASS":
        return {"python_compatible": False, "dependency_coverage": 0.0, "missing": [], "version_incompatible": [], "contract_compatible": False}
    py_ok = True
    if contract.get("requires_python"):
        py_ok = Version(probe["python_version"]) in SpecifierSet(contract["requires_python"])
    packages = {str(k).lower(): str(v) for k, v in probe.get("packages", {}).items()}
    missing: list[str] = []
    incompatible: list[str] = []
    total = 0
    matched = 0
    for raw in contract.get("dependencies", []):
        try:
            req = Requirement(raw)
        except Exception:
            continue
        if req.marker and not req.marker.evaluate():
            continue
        total += 1
        name = req.name.lower()
        installed = packages.get(name)
        if installed is None:
            missing.append(req.name)
            continue
        if req.specifier and Version(installed) not in req.specifier:
            incompatible.append(f"{req.name}=={installed} not in {req.specifier}")
            continue
        matched += 1
    coverage = 1.0 if total == 0 else matched / total
    return {
        "python_compatible": py_ok,
        "dependency_coverage": coverage,
        "missing": sorted(missing),
        "version_incompatible": sorted(incompatible),
        "contract_compatible": bool(py_ok and not missing and not incompatible),
    }


def choose_candidate(row3b: dict[str, str], row3c: dict[str, str] | None) -> tuple[str, str]:
    mapping_status = row3b["mapping_status"]
    selected = row3b.get("selected_runtime_prefix", "")
    if mapping_status in {"DIRECT_PROJECT_RUNTIME", "EXISTING_VENV_CANDIDATE"} and selected:
        return selected, mapping_status
    if row3c:
        candidate = row3c.get("best_candidate_runtime", "")
        if candidate:
            return candidate, row3c.get("classification", "PHASE3C_CANDIDATE")
    return "", mapping_status


def lane_from(row3b: dict[str, str], row3c: dict[str, str] | None, contract_eval: dict[str, Any], probe: dict[str, Any]) -> tuple[str, bool, int, str]:
    mapping_status = row3b["mapping_status"]
    phase2_statuses = set(parse_json_cell(row3b.get("selected_phase2_statuses", "")))
    torch_versions = list(parse_json_cell(row3b.get("selected_torch_versions", "")))

    if mapping_status == "DIRECT_PROJECT_RUNTIME" and contract_eval.get("contract_compatible"):
        if "CUDA_KERNEL_PASS" in phase2_statuses:
            if any(str(v).startswith("2.13") for v in torch_versions):
                return "CURRENT_MODERN_GPU_CANDIDATE", True, 10, "Direct venv, declared dependencies compatible, CUDA kernel PASS, Torch 2.13 family."
            return "CURRENT_LEGACY_GPU_COMPAT", True, 20, "Direct venv, declared dependencies compatible, CUDA kernel PASS, pre-2.13 Torch family."
        if "IMPORT_VERIFIED_CPU" in phase2_statuses:
            return "CURRENT_CPU_LEGACY", True, 30, "Direct venv, declared dependencies compatible, CPU import verified."
        return "DIRECT_RUNTIME_SMOKE_CANDIDATE", True, 35, "Direct venv and declared dependencies compatible; Phase 4 smoke required."

    if row3c:
        c = row3c.get("classification", "")
        if c == "REUSABLE_COMPATIBLE_VENV" and contract_eval.get("contract_compatible"):
            return "REUSABLE_COMPATIBLE_VENV", True, 40, "Existing separate venv satisfies declared Python/direct dependency metadata; formal smoke still required."
        if c == "BROKEN_DECLARED_RUNTIME":
            return "REPAIR_DECLARED_RUNTIME", False, 80, "Declared venv contains broken Python symlink evidence; repair/recreate before formal certification."
        if c == "CANDIDATE_REQUIRES_SEPARATE_FORMAL_LANE":
            return "SEPARATE_FORMAL_LANE_REQUIRED", False, 70, "Related venv exists but declared dependency contract is not fully compatible."

    if mapping_status == "EXISTING_VENV_CANDIDATE":
        if contract_eval.get("contract_compatible"):
            return "EXISTING_VENV_METADATA_COMPATIBLE", True, 45, "Existing candidate venv satisfies declared metadata; formal smoke required before adoption."
        return "EXISTING_VENV_FORMAL_COMPAT_REQUIRED", False, 65, "Existing candidate is related but metadata contract is incomplete or incompatible."

    if mapping_status == "MULTIPLE_VENV_CANDIDATES":
        return "AMBIGUOUS_FORMAL_LANE", False, 75, "Multiple venv candidates remain; do not silently select one."
    return "NO_FORMAL_RUNTIME_READY", False, 90, "No formal runtime lane is ready for model smoke."


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    source_sha = run(["git", "-C", str(SOURCE_WT), "rev-parse", "HEAD"]).stdout.strip()
    if source_sha != EXPECTED_SOURCE_SHA:
        raise SystemExit(f"source SHA mismatch: {source_sha}")
    if run(["git", "-C", str(SOURCE_WT), "status", "--porcelain"]).stdout.strip():
        raise SystemExit("source audit worktree is dirty")

    branch = run(["git", "-C", str(HANDOFF_WT), "branch", "--show-current"]).stdout.strip()
    if branch != BRANCH:
        raise SystemExit(f"wrong handoff branch: {branch}")
    if run(["git", "-C", str(HANDOFF_WT), "status", "--porcelain"]).stdout.strip():
        raise SystemExit("handoff worktree is dirty before Phase 3D")

    rows3b = read_tsv(PHASE3B / "environment-venv-mapping.tsv")
    rows3c = read_tsv(PHASE3C / "runtime-gap-review.tsv")
    by3c = {r["environment"]: r for r in rows3c}
    if len(rows3b) != 29:
        raise SystemExit(f"expected 29 Phase3B environment rows, found {len(rows3b)}")

    output: list[dict[str, Any]] = []
    probe_cache: dict[str, dict[str, Any]] = {}

    for row3b in rows3b:
        env = row3b["environment"]
        row3c = by3c.get(env)
        candidate, candidate_source = choose_candidate(row3b, row3c)
        contract = source_contract(env)
        if candidate:
            probe = probe_cache.setdefault(candidate, package_probe(candidate))
            evaluation = compare_contract(contract, probe)
        else:
            probe = {"status": "NO_CANDIDATE", "python_version": "", "packages": {}}
            evaluation = {"python_compatible": False, "dependency_coverage": 0.0, "missing": [], "version_incompatible": [], "contract_compatible": False}
        lane, smoke_allowed, priority, reason = lane_from(row3b, row3c, evaluation, probe)
        output.append({
            "environment": env,
            "mapping_status": row3b["mapping_status"],
            "phase3c_classification": row3c.get("classification", "") if row3c else "",
            "candidate_runtime": candidate,
            "candidate_source": candidate_source,
            "candidate_probe_status": probe.get("status", ""),
            "candidate_python_version": probe.get("python_version", ""),
            "python_compatible": evaluation.get("python_compatible"),
            "dependency_coverage": evaluation.get("dependency_coverage"),
            "missing_dependencies": evaluation.get("missing", []),
            "version_incompatible": evaluation.get("version_incompatible", []),
            "declared_contract_compatible": evaluation.get("contract_compatible"),
            "phase2_statuses": parse_json_cell(row3b.get("selected_phase2_statuses", "")),
            "torch_versions": parse_json_cell(row3b.get("selected_torch_versions", "")),
            "cuda_builds": parse_json_cell(row3b.get("selected_cuda_builds", "")),
            "lane": lane,
            "phase4_smoke_allowed": smoke_allowed,
            "phase4_priority": priority,
            "decision_reason": reason,
        })

    output.sort(key=lambda r: (int(r["phase4_priority"]), r["environment"]))
    lane_counts = Counter(r["lane"] for r in output)
    ready = [r for r in output if r["phase4_smoke_allowed"]]
    blocked = [r for r in output if not r["phase4_smoke_allowed"]]

    fields = [
        "environment", "mapping_status", "phase3c_classification", "candidate_runtime", "candidate_source",
        "candidate_probe_status", "candidate_python_version", "python_compatible", "dependency_coverage",
        "missing_dependencies", "version_incompatible", "declared_contract_compatible", "phase2_statuses",
        "torch_versions", "cuda_builds", "lane", "phase4_smoke_allowed", "phase4_priority", "decision_reason",
    ]
    write_tsv(OUT / "runtime-lane-plan.tsv", output, fields)
    write_tsv(OUT / "phase4-ready-queue.tsv", ready, fields)
    write_tsv(OUT / "blocked-runtime-lanes.tsv", blocked, fields)

    summary = {
        "schema_version": 1,
        "source_sha": EXPECTED_SOURCE_SHA,
        "source_environment_count": len(output),
        "phase3c_review_target_count": len(rows3c),
        "lane_counts": dict(sorted(lane_counts.items())),
        "phase4_smoke_allowed_count": len(ready),
        "phase4_blocked_count": len(blocked),
        "modern_gpu_candidate_count": lane_counts.get("CURRENT_MODERN_GPU_CANDIDATE", 0),
        "legacy_gpu_compat_count": lane_counts.get("CURRENT_LEGACY_GPU_COMPAT", 0),
        "cpu_legacy_count": lane_counts.get("CURRENT_CPU_LEGACY", 0),
        "dependencies_modified": False,
        "model_checkpoint_loaded": False,
        "formal_runtime_certification": False,
        "modern_target_not_migrated": True,
        "interpretation": "Phase 3D selects current runtime lanes and Phase 4 smoke eligibility only. It does not upgrade Python/Torch/CUDA or certify any model.",
    }
    dump_json(OUT / "summary.json", summary)

    lines = [
        "# Phase 3D Runtime Lane Selection", "",
        f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
        f"- source environments: {len(output)}",
        f"- Phase 4 smoke allowed now: {len(ready)}",
        f"- blocked pending repair/formal-lane work: {len(blocked)}", "",
        "## Lane counts", "",
    ]
    for name, count in sorted(lane_counts.items()):
        lines.append(f"- `{name}`: {count}")
    lines += [
        "", "## Boundary", "",
        "This phase performs metadata/runtime-lane selection only.",
        "No dependency is installed or modified. No checkpoint is loaded and no forecast is executed.",
        "", "## Next", "",
        "Start Phase 4A with the highest-priority smoke-allowed runtimes.",
        "Each Phase 4 smoke must verify load, real input, inference, shape, finite output, requested/effective device, GPU PID/VRAM, and CPU fallback.",
    ]
    (OUT / "PHASE3D_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff["estimated_progress_percent"] = 40
    handoff["current_phase"] = "phase3d_completed_phase4a_next"
    handoff.setdefault("completed_phases", {})["phase3d"] = "VERIFIED"
    handoff["phase3d"] = summary
    handoff_path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    current = HANDOFF / "CURRENT_STATUS.md"
    status_lines = [
        "# Loto Forecast Runtime Audit Handoff", "",
        f"Updated: {datetime.now().astimezone().isoformat()}", "",
        "## Current overall status", "",
        "- overall: `PARTIALLY_VERIFIED`",
        "- estimated progress: `40%`",
        "- current phase: `Phase 3D completed / Phase 4A smoke next`", "",
        "## Completed", "",
        "- Phase 0: VERIFIED", "- Phase 1 / 1B: VERIFIED", "- Phase 2: VERIFIED",
        "- Phase 3: PARTIALLY_VERIFIED", "- Phase 3B: VERIFIED", "- Phase 3C: VERIFIED", "- Phase 3D: VERIFIED", "",
        "## Phase 3D lane counts", "",
    ]
    for name, count in sorted(lane_counts.items()):
        status_lines.append(f"- {name}: {count}")
    status_lines += [
        "", f"- Phase 4 smoke allowed now: {len(ready)}",
        f"- blocked pending repair/formal lane: {len(blocked)}", "",
        "## Next", "",
        "Begin Phase 4A real checkpoint/load-inference smoke on the ready queue.",
        "Do not treat Phase 3D metadata compatibility as formal model certification.",
    ]
    current.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    subprocess.run(["git", "-C", str(HANDOFF_WT), "add", "handoff"], check=True)
    if subprocess.run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"]).returncode != 0:
        subprocess.run(["git", "-C", str(HANDOFF_WT), "commit", "-m", f"audit: publish Phase 3D runtime lane selection {datetime.now().strftime('%Y%m%d-%H%M%S')}"] , check=True)
    subprocess.run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], check=True)
    subprocess.run(["git", "-C", str(HANDOFF_WT), "fetch", "origin", BRANCH], check=True)
    local_head = run(["git", "-C", str(HANDOFF_WT), "rev-parse", "HEAD"]).stdout.strip()
    remote_head = run(["git", "-C", str(HANDOFF_WT), "rev-parse", f"origin/{BRANCH}"]).stdout.strip()
    if local_head != remote_head:
        raise SystemExit(f"remote verification failed: local={local_head} remote={remote_head}")

    print("=" * 60)
    print("PHASE3D_AND_HANDOFF=PASS")
    print(f"HANDOFF_HEAD={local_head}")
    print(f"SUMMARY={OUT / 'summary.json'}")
    print(f"REPORT={OUT / 'PHASE3D_REPORT.md'}")
    print("NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 3D結果を確認して次へ進めてください")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
