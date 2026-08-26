#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("LOTO_ROOT", "/mnt/e/env/ts/loto_forecast_platform"))
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
BRANCH = "ops/runtime-audit-handoff"
HANDOFF = HANDOFF_WT / "handoff"
PHASE3B = HANDOFF / "phase3b"
OUT = HANDOFF / "phase3c"

try:
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
except Exception:
    Requirement = None
    SpecifierSet = None
    Version = None


def run(cmd: list[str], *, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            payload: dict[str, Any] = {}
            for field in fields:
                value = row.get(field, "")
                if isinstance(value, (list, tuple, dict, set)):
                    if isinstance(value, set):
                        value = sorted(value)
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                payload[field] = value
            writer.writerow(payload)


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def dependency_name(spec: str) -> str:
    if Requirement is not None:
        try:
            return normalize_name(Requirement(spec).name)
        except Exception:
            pass
    match = re.match(r"^\s*([A-Za-z0-9_.-]+)", spec)
    return normalize_name(match.group(1)) if match else ""


def dependency_specifier(spec: str) -> str:
    if Requirement is not None:
        try:
            return str(Requirement(spec).specifier)
        except Exception:
            return ""
    return ""


def python_matches(version: str, requires_python: str) -> bool | None:
    if not version or not requires_python or SpecifierSet is None or Version is None:
        return None
    try:
        return Version(version) in SpecifierSet(requires_python)
    except Exception:
        return None


def version_matches(version: str, specifier: str) -> bool | None:
    if not version or not specifier or SpecifierSet is None or Version is None:
        return None
    try:
        return Version(version) in SpecifierSet(specifier)
    except Exception:
        return None


def choose_python(prefix: Path) -> Path | None:
    for name in ("python", "python3"):
        path = prefix / "bin" / name
        if path.exists() and os.access(path, os.X_OK):
            return path
    return None


RUNTIME_PROBE = r'''
from __future__ import annotations
import importlib.metadata
import json
import platform
import sys

packages = {}
for dist in importlib.metadata.distributions():
    try:
        name = (dist.metadata.get("Name") or "").strip().lower().replace("_", "-").replace(".", "-")
        if name:
            packages[name] = str(dist.version or "")
    except Exception:
        pass

print("__PHASE3C__" + json.dumps({
    "python_version": platform.python_version(),
    "sys_prefix": sys.prefix,
    "packages": packages,
}, sort_keys=True))
'''


def probe_runtime(prefix: Path) -> dict[str, Any]:
    py = choose_python(prefix)
    if py is None:
        return {
            "runtime_prefix": str(prefix),
            "probe_status": "NO_EXECUTABLE_PYTHON",
            "python_version": "",
            "packages": {},
        }
    try:
        proc = subprocess.run(
            [str(py), "-I", "-c", RUNTIME_PROBE],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return {
            "runtime_prefix": str(prefix),
            "probe_status": "TIMEOUT",
            "python_version": "",
            "packages": {},
        }
    marker = "__PHASE3C__"
    payload = None
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(marker):
            payload = json.loads(line[len(marker):])
            break
    if payload is None:
        return {
            "runtime_prefix": str(prefix),
            "probe_status": "INVALID_OUTPUT",
            "python_version": "",
            "packages": {},
            "stderr_tail": proc.stderr[-2000:],
        }
    return {
        "runtime_prefix": str(prefix),
        "probe_status": "PASS" if proc.returncode == 0 else "PROCESS_FAILED",
        "python_version": payload.get("python_version", ""),
        "reported_sys_prefix": payload.get("sys_prefix", ""),
        "packages": payload.get("packages", {}),
        "stderr_tail": proc.stderr[-2000:],
    }


def source_environment_defs() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for pp in sorted(SOURCE_WT.glob("environments/*/pyproject.toml")):
        data = tomllib.loads(pp.read_text(encoding="utf-8"))
        project = data.get("project", {})
        rel = str(pp.parent.relative_to(SOURCE_WT))
        deps = list(project.get("dependencies", []))
        result[rel] = {
            "environment": rel,
            "name": pp.parent.name,
            "project_name": project.get("name", ""),
            "requires_python": project.get("requires-python", ""),
            "dependencies": deps,
            "dependency_names": sorted({dependency_name(x) for x in deps if dependency_name(x)}),
        }
    return result


def broken_paths_by_environment() -> dict[str, list[dict[str, str]]]:
    rows = read_tsv(PHASE3B / "raw-interpreter-paths.tsv")
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("probe_status") != "BROKEN_SYMLINK":
            continue
        raw = row.get("raw_path", "")
        match = re.search(r"/(environments/[^/]+)/\.venv/bin/python3?$", raw)
        if match:
            env = match.group(1)
            result.setdefault(env, []).append(
                {
                    "raw_path": raw,
                    "symlink_target": row.get("symlink_target", ""),
                }
            )
    return result


def candidate_score(
    env: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    packages: dict[str, str] = runtime.get("packages", {})
    deps: list[str] = env["dependencies"]
    direct_names = [dependency_name(x) for x in deps if dependency_name(x)]

    present: list[str] = []
    missing: list[str] = []
    version_ok: list[str] = []
    version_bad: list[str] = []
    version_unknown: list[str] = []

    for dep in deps:
        name = dependency_name(dep)
        if not name:
            continue
        installed = packages.get(name)
        if installed is None:
            missing.append(name)
            continue
        present.append(name)
        specifier = dependency_specifier(dep)
        verdict = version_matches(installed, specifier)
        if verdict is True:
            version_ok.append(f"{name}=={installed}")
        elif verdict is False:
            version_bad.append(f"{name}=={installed} not in {specifier}")
        else:
            version_unknown.append(f"{name}=={installed}")

    python_ok = python_matches(runtime.get("python_version", ""), env.get("requires_python", ""))
    coverage = (len(present) / len(direct_names)) if direct_names else 1.0

    score = round(coverage * 1000)
    if python_ok is True:
        score += 100
    elif python_ok is False:
        score -= 500
    score -= 100 * len(version_bad)

    if coverage == 1.0 and python_ok is not False and not version_bad:
        compatibility = "DECLARED_DEPENDENCIES_COMPATIBLE"
    elif coverage >= 0.5 and python_ok is not False:
        compatibility = "PARTIAL_DEPENDENCY_MATCH"
    else:
        compatibility = "INCOMPATIBLE_OR_LOW_COVERAGE"

    return {
        "runtime_prefix": runtime["runtime_prefix"],
        "python_version": runtime.get("python_version", ""),
        "python_compatible": python_ok,
        "dependency_coverage": coverage,
        "present_dependencies": sorted(present),
        "missing_dependencies": sorted(missing),
        "version_compatible": sorted(version_ok),
        "version_incompatible": sorted(version_bad),
        "version_unchecked": sorted(version_unknown),
        "compatibility": compatibility,
        "score": score,
    }


def update_integrity() -> None:
    manifest_rows: list[dict[str, Any]] = []
    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or path.name in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            continue
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_rows.append(
            {"path": str(path.relative_to(OUT)), "size": path.stat().st_size, "sha256": h}
        )
    dump_json(
        OUT / "ARTIFACT_MANIFEST.json",
        {"schema_version": 1, "artifact_count": len(manifest_rows), "artifacts": manifest_rows},
    )
    lines: list[str] = []
    for path in sorted(HANDOFF.rglob("*")):
        if not path.is_file() or path == HANDOFF / "SHA256SUMS":
            continue
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(HANDOFF_WT)}")
    (HANDOFF / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_handoff(summary: dict[str, Any], run_id: str) -> None:
    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = load_json(handoff_path)
    handoff["handoff_run_id"] = run_id
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff["estimated_progress_percent"] = 38
    handoff["completed_phases"]["phase3c"] = "VERIFIED"
    handoff["current_phase"] = "phase3c_completed_pending_phase4_lane_selection"
    handoff["phase3c"] = summary
    dump_json(handoff_path, handoff)

    current = f"""# Loto Forecast Runtime Audit Handoff

Updated: {datetime.now().astimezone().isoformat()}

## Current overall status

- overall: `PARTIALLY_VERIFIED`
- estimated progress: `38%`
- current phase: `Phase 3C completed / Phase 4 lane selection next`

## Completed

- Phase 0: VERIFIED
- Phase 1 / 1B: VERIFIED
- Phase 2: VERIFIED
- Phase 3: PARTIALLY_VERIFIED
- Phase 3B: VERIFIED
- Phase 3C: VERIFIED

## Phase 3C runtime gap review

- source environments: {summary['source_environment_count']}
- unresolved reviewed: {summary['reviewed_unresolved_count']}
- ambiguous reviewed: {summary['reviewed_ambiguous_count']}
- broken declared runtimes: {summary['classification_counts'].get('BROKEN_DECLARED_RUNTIME', 0)}
- reusable compatible candidates: {summary['classification_counts'].get('REUSABLE_COMPATIBLE_VENV', 0)}
- candidate exists but incompatible/partial: {summary['classification_counts'].get('CANDIDATE_REQUIRES_SEPARATE_FORMAL_LANE', 0)}
- no runtime found: {summary['classification_counts'].get('NO_RUNTIME_FOUND', 0)}

## Next

Use Phase 3C evidence to select formal Modern GPU and Legacy compatibility lanes.
Do not install or overwrite unresolved environments until the lane decision is recorded.
Then begin Phase 4 real checkpoint load/inference smoke certification.

## Formal runtime certification

Not yet complete. Phase 4 must verify checkpoint load, real input, inference,
output shape, finite values, requested/effective device, GPU PID/VRAM,
CPU fallback, and save/reload where applicable.
"""
    (HANDOFF / "CURRENT_STATUS.md").write_text(current, encoding="utf-8")


def git_publish(run_id: str) -> str:
    status = run(["git", "-C", str(HANDOFF_WT), "status", "--porcelain"]).stdout.strip()
    # Changes are expected now, but no unrelated changes may exist before script start.
    run(["git", "-C", str(HANDOFF_WT), "add", "handoff"])
    staged = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"], check=False)
    if staged.returncode != 0:
        run(
            [
                "git",
                "-C",
                str(HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 3C runtime gap review {run_id}",
            ]
        )
    run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH])
    run(["git", "-C", str(HANDOFF_WT), "fetch", "origin", BRANCH])
    local = run(["git", "-C", str(HANDOFF_WT), "rev-parse", "HEAD"]).stdout.strip()
    remote = run(["git", "-C", str(HANDOFF_WT), "rev-parse", f"origin/{BRANCH}"]).stdout.strip()
    if local != remote:
        raise RuntimeError(f"remote verification mismatch local={local} remote={remote}")
    return local


def main() -> int:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    branch = run(["git", "-C", str(HANDOFF_WT), "branch", "--show-current"]).stdout.strip()
    if branch != BRANCH:
        raise RuntimeError(f"wrong handoff branch: {branch}")
    if run(["git", "-C", str(HANDOFF_WT), "status", "--porcelain"]).stdout.strip():
        raise RuntimeError("handoff worktree must be clean before Phase 3C")

    run(["git", "-C", str(HANDOFF_WT), "fetch", "--prune", "origin"])
    run(["git", "-C", str(HANDOFF_WT), "pull", "--ff-only", "origin", BRANCH])

    handoff = load_json(HANDOFF / "HANDOFF.json")
    expected_sha = handoff["source_sha"]
    source_sha = run(["git", "-C", str(SOURCE_WT), "rev-parse", "HEAD"]).stdout.strip()
    if source_sha != expected_sha:
        raise RuntimeError(f"source SHA mismatch expected={expected_sha} actual={source_sha}")
    if run(["git", "-C", str(SOURCE_WT), "status", "--porcelain"]).stdout.strip():
        raise RuntimeError("source audit worktree is dirty")

    defs = source_environment_defs()
    if len(defs) != 29:
        raise RuntimeError(f"expected 29 environment definitions, got {len(defs)}")

    unresolved_rows = read_tsv(PHASE3B / "unresolved-environments.tsv")
    ambiguous_rows = read_tsv(PHASE3B / "multiple-venv-candidates.tsv")
    identity_rows = read_tsv(PHASE3B / "runtime-identities.tsv")
    broken = broken_paths_by_environment()

    runtime_prefixes = [
        Path(row["runtime_prefix"])
        for row in identity_rows
        if row.get("classification") == "VIRTUAL_ENVIRONMENT"
    ]
    runtime_probes = {str(prefix): probe_runtime(prefix) for prefix in runtime_prefixes}

    review_targets = [row["environment"] for row in unresolved_rows] + [
        row["environment"] for row in ambiguous_rows
    ]

    detail_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    for env_name in review_targets:
        env = defs[env_name]
        expected_prefix = REPO / env_name / ".venv"
        broken_links = broken.get(env_name, [])

        scored = [candidate_score(env, runtime_probes[str(prefix)]) for prefix in runtime_prefixes]
        # Keep only candidates with at least one declared dependency present or an environment-name match.
        filtered = [
            x
            for x in scored
            if x["dependency_coverage"] > 0
            or env["name"].lower() in x["runtime_prefix"].lower()
        ]
        filtered.sort(key=lambda x: (-x["score"], x["runtime_prefix"]))

        for candidate in filtered[:10]:
            candidate_rows.append({"environment": env_name, **candidate})

        best = filtered[0] if filtered else None

        if broken_links:
            classification = "BROKEN_DECLARED_RUNTIME"
        elif best and best["compatibility"] == "DECLARED_DEPENDENCIES_COMPATIBLE":
            classification = "REUSABLE_COMPATIBLE_VENV"
        elif best:
            classification = "CANDIDATE_REQUIRES_SEPARATE_FORMAL_LANE"
        else:
            classification = "NO_RUNTIME_FOUND"

        detail_rows.append(
            {
                "environment": env_name,
                "project_name": env["project_name"],
                "requires_python": env["requires_python"],
                "classification": classification,
                "expected_prefix": str(expected_prefix),
                "expected_prefix_exists": expected_prefix.exists(),
                "broken_symlink_count": len(broken_links),
                "broken_symlinks": broken_links,
                "best_candidate_runtime": best["runtime_prefix"] if best else "",
                "best_candidate_score": best["score"] if best else "",
                "best_candidate_compatibility": best["compatibility"] if best else "",
                "best_candidate_dependency_coverage": best["dependency_coverage"] if best else "",
                "best_candidate_python_compatible": best["python_compatible"] if best else "",
                "best_candidate_missing_dependencies": best["missing_dependencies"] if best else [],
                "best_candidate_version_incompatible": best["version_incompatible"] if best else [],
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    write_tsv(
        OUT / "runtime-gap-review.tsv",
        detail_rows,
        [
            "environment",
            "project_name",
            "requires_python",
            "classification",
            "expected_prefix",
            "expected_prefix_exists",
            "broken_symlink_count",
            "broken_symlinks",
            "best_candidate_runtime",
            "best_candidate_score",
            "best_candidate_compatibility",
            "best_candidate_dependency_coverage",
            "best_candidate_python_compatible",
            "best_candidate_missing_dependencies",
            "best_candidate_version_incompatible",
        ],
    )
    write_tsv(
        OUT / "candidate-compatibility.tsv",
        candidate_rows,
        [
            "environment",
            "runtime_prefix",
            "python_version",
            "python_compatible",
            "dependency_coverage",
            "compatibility",
            "score",
            "present_dependencies",
            "missing_dependencies",
            "version_compatible",
            "version_incompatible",
            "version_unchecked",
        ],
    )

    counts = Counter(row["classification"] for row in detail_rows)
    summary = {
        "schema_version": 1,
        "source_sha": expected_sha,
        "phase3b_runtime_identity_method": "sys.prefix",
        "source_environment_count": len(defs),
        "reviewed_unresolved_count": len(unresolved_rows),
        "reviewed_ambiguous_count": len(ambiguous_rows),
        "review_target_count": len(review_targets),
        "runtime_identity_count": len(runtime_prefixes),
        "classification_counts": dict(sorted(counts.items())),
        "dependency_compatibility_is_candidate_evidence_only": True,
        "dependencies_modified": False,
        "model_checkpoint_loaded": False,
        "formal_runtime_certification": False,
    }
    dump_json(OUT / "summary.json", summary)

    report_lines = [
        "# Phase 3C Runtime Gap Review",
        "",
        f"- source SHA: `{expected_sha}`",
        f"- unresolved environments reviewed: {len(unresolved_rows)}",
        f"- ambiguous environments reviewed: {len(ambiguous_rows)}",
        f"- sys.prefix runtime identities considered: {len(runtime_prefixes)}",
        "",
        "## Classification",
        "",
    ]
    for key, value in sorted(counts.items()):
        report_lines.append(f"- `{key}`: {value}")
    report_lines += [
        "",
        "## Interpretation",
        "",
        "`BROKEN_DECLARED_RUNTIME` means the declared project venv has broken Python symlink evidence.",
        "",
        "`REUSABLE_COMPATIBLE_VENV` means an existing venv matches the declared Python constraint and direct dependencies at the metadata level. It is not yet formal model certification.",
        "",
        "`CANDIDATE_REQUIRES_SEPARATE_FORMAL_LANE` means a related existing venv exists but does not fully satisfy the declared dependency contract, so it must not silently replace the formal lane.",
        "",
        "`NO_RUNTIME_FOUND` means no sufficiently related existing venv was found from current runtime identities.",
        "",
        "No dependency was installed or modified. No model checkpoint was loaded.",
    ]
    (OUT / "PHASE3C_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    update_handoff(summary, run_id)
    update_integrity()

    # Size gate before commit.
    oversized = [p for p in HANDOFF.rglob("*") if p.is_file() and p.stat().st_size >= 95_000_000]
    if oversized:
        raise RuntimeError(f"handoff file >=95MB: {oversized[0]}")

    head = git_publish(run_id)

    print("============================================================")
    print("PHASE3C_AND_HANDOFF=PASS")
    print(f"HANDOFF_HEAD={head}")
    print(f"SUMMARY={OUT / 'summary.json'}")
    print(f"REPORT={OUT / 'PHASE3C_REPORT.md'}")
    print("NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 3C結果を確認して次へ進めてください")
    print("============================================================")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE3C_FAILED={type(exc).__name__}: {exc}", file=sys.stderr)
        raise
