#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "phase4a_darts_gpu_smoke.py"

spec = importlib.util.spec_from_file_location("phase4a_impl", TARGET)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load phase4a_darts_gpu_smoke.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def safe_publish(summary: dict) -> str:
    # Never put trained model binaries or derived real-data rows into Git.
    if mod.HANDOFF_OUT.exists():
        shutil.rmtree(mod.HANDOFF_OUT)
    mod.HANDOFF_OUT.mkdir(parents=True, exist_ok=True)

    safe_names = {
        "summary.json",
        "PHASE4A_REPORT.md",
        "ARTIFACT_MANIFEST.json",
        "request.json",
        "response.json",
        "discover-request.json",
        "discover-response.json",
        "data-evidence.json",
        "selected-model.json",
        "torch-probe.json",
        "gpu-before.json",
        "gpu-after.json",
        "gpu-process-samples.jsonl",
        "provider.stdout.log",
        "provider.stderr.log",
        "discover.stdout.log",
        "discover.stderr.log",
    }
    safe_suffixes = {".json", ".jsonl", ".md", ".log", ".txt", ".tsv"}

    for src in sorted(mod.LOCAL_OUT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(mod.LOCAL_OUT)
        if rel.name == "smoke-input.csv":
            continue
        if "models" in rel.parts:
            continue
        if rel.name not in safe_names and rel.suffix.lower() not in safe_suffixes:
            continue
        dst = mod.HANDOFF_OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    handoff_path = mod.HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["handoff_run_id"] = mod.RUN_ID
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff.setdefault("completed_phases", {})["phase4a"] = summary["status"]
    handoff["current_phase"] = (
        "phase4a_darts_gpu_verified_phase4b_next"
        if summary["status"] == "VERIFIED"
        else "phase4a_darts_gpu_requires_review"
    )
    handoff["estimated_progress_percent"] = 44 if summary["status"] == "VERIFIED" else 40
    handoff["phase4a"] = summary
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    current = mod.HANDOFF / "CURRENT_STATUS.md"
    current.write_text(
        "\n".join(
            [
                "# Loto Forecast Runtime Audit Handoff",
                "",
                f"Updated: {datetime.now().astimezone().isoformat()}",
                "",
                "## Current overall status",
                "",
                f"- estimated progress: `{handoff['estimated_progress_percent']}%`",
                f"- Phase 4A Darts GPU smoke: `{summary['status']}`",
                f"- source SHA: `{mod.EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 4A",
                "",
                f"- model: `{summary.get('model_public_name')}`",
                f"- runtime: `{mod.RUNTIME}`",
                f"- real data source: `{summary.get('data', {}).get('source_path')}`",
                f"- real-data source SHA-256: `{summary.get('data', {}).get('source_sha256')}`",
                f"- derived smoke-data SHA-256: `{summary.get('data', {}).get('derived_sha256')}`",
                f"- prediction shape/finite: `{summary.get('validation', {}).get('checks', {}).get('prediction_shape')}` / `{summary.get('validation', {}).get('checks', {}).get('prediction_finite')}`",
                f"- GPU PID observed: `{summary.get('validation', {}).get('checks', {}).get('gpu_pid_observed')}`",
                f"- peak provider VRAM MiB: `{summary.get('gpu', {}).get('peak_matching_gpu_memory_mib')}`",
                f"- save/reload certified: `{summary.get('validation', {}).get('checks', {}).get('save_reload_certified')}`",
                "",
                "## Evidence policy",
                "",
                "Trained model binaries and derived real-data rows remain local. Git handoff contains only metadata, hashes, request/response, metrics, logs, and GPU evidence.",
                "",
                "## Next",
                "",
                "If VERIFIED, continue Phase 4B across the remaining ready queue. If FAILED, inspect Phase 4A evidence before modifying dependencies.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    file_sizes = mod.HANDOFF / "FILE_SIZES.tsv"
    rows = []
    for path in mod.HANDOFF.rglob("*"):
        if path.is_file():
            rows.append((path.stat().st_size, path))
    file_sizes.write_text(
        "".join(f"{size}\t{path}\n" for size, path in sorted(rows, reverse=True)),
        encoding="utf-8",
    )
    if any(size >= 95_000_000 for size, _ in rows):
        raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")

    sums = mod.HANDOFF / "SHA256SUMS"
    lines = []
    for path in sorted(mod.HANDOFF.rglob("*")):
        if path.is_file() and path != sums:
            lines.append(f"{mod.sha256_file(path)}  {path.relative_to(mod.HANDOFF_WT)}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")

    add = mod.run(["git", "-C", str(mod.HANDOFF_WT), "add", "handoff"], timeout=60)
    if add.returncode != 0:
        raise RuntimeError(f"HANDOFF_ADD_FAILED: {add.stderr.strip()}")

    diff = mod.run(
        ["git", "-C", str(mod.HANDOFF_WT), "diff", "--cached", "--quiet"],
        timeout=30,
    )
    if diff.returncode not in (0, 1):
        raise RuntimeError(f"HANDOFF_DIFF_FAILED: {diff.stderr.strip()}")
    if diff.returncode == 1:
        commit = mod.run(
            [
                "git",
                "-C",
                str(mod.HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 4A Darts GPU smoke {mod.RUN_ID}",
            ],
            timeout=120,
        )
        if commit.returncode != 0:
            raise RuntimeError(f"HANDOFF_COMMIT_FAILED: {commit.stderr.strip()}")

    push = mod.run(
        ["git", "-C", str(mod.HANDOFF_WT), "push", "origin", mod.BRANCH],
        timeout=180,
    )
    if push.returncode != 0:
        raise RuntimeError(f"HANDOFF_PUSH_FAILED: {push.stderr.strip()}")

    fetch = mod.run(
        ["git", "-C", str(mod.HANDOFF_WT), "fetch", "origin", mod.BRANCH],
        timeout=120,
    )
    if fetch.returncode != 0:
        raise RuntimeError(f"HANDOFF_FETCH_FAILED: {fetch.stderr.strip()}")

    local = mod.run(["git", "-C", str(mod.HANDOFF_WT), "rev-parse", "HEAD"], timeout=30)
    remote = mod.run(
        ["git", "-C", str(mod.HANDOFF_WT), "rev-parse", f"origin/{mod.BRANCH}"],
        timeout=30,
    )
    if local.returncode != 0 or remote.returncode != 0 or local.stdout.strip() != remote.stdout.strip():
        raise RuntimeError("HANDOFF_REMOTE_VERIFY_FAILED")
    return local.stdout.strip()


mod.publish = safe_publish
raise SystemExit(mod.main())
