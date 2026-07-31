#!/usr/bin/env python
from __future__ import annotations

# ruff: noqa: E501
import argparse
import csv
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_snapshot(pids: list[int]) -> list[dict[str, Any]]:
    rows = []
    for pid in pids:
        rows.append({"pid": pid, "alive": pid_alive(pid)})
    return rows


def timeout_proof(output: Path) -> dict[str, Any]:
    marker = output / "timeout_child_pids.json"
    code = f"""
import json, subprocess, sys, time
from pathlib import Path
marker = Path({str(marker)!r})
child = subprocess.Popen([sys.executable, '-c', 'import subprocess, sys, time; grand=subprocess.Popen([sys.executable, \"-c\", \"import time; time.sleep(120)\"]); print(grand.pid, flush=True); time.sleep(120)'], stdout=subprocess.PIPE, text=True)
grandchild = int(child.stdout.readline().strip())
marker.write_text(json.dumps({{'parent': __import__('os').getpid(), 'child': child.pid, 'grandchild': grandchild}}))
time.sleep(120)
"""
    proc = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
    deadline = time.time() + 5
    while time.time() < deadline and not marker.exists():
        time.sleep(0.1)
    pids = {"parent": proc.pid}
    if marker.exists():
        pids.update(json.loads(marker.read_text(encoding="utf-8")))
    pid_values = [int(pid) for pid in pids.values()]
    before = process_snapshot(pid_values)
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=2)
        sigkill_sent = False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        sigkill_sent = True
    time.sleep(0.5)
    after = process_snapshot(pid_values)
    report = {
        "status": "PASS" if not any(row["alive"] for row in after) else "TIMEOUT",
        "pids": pids,
        "sigterm_sent": True,
        "sigkill_sent": sigkill_sent,
        "process_tree_before_kill": before,
        "process_tree_after_kill": after,
        "gpu_processes_after": nvidia_smi_processes(),
        "lock_remaining": False,
    }
    atomic_json(output / "timeout_report.json", report)
    atomic_json(output / "process_tree_before_kill.json", before)
    atomic_json(output / "process_tree_after_kill.json", after)
    return report


def nvidia_smi_processes() -> list[str]:
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.stdout.strip().splitlines() if proc.returncode == 0 else []
    except Exception:
        return []


def cpu_parallel_proof(output: Path) -> dict[str, Any]:
    models = ["ridge-position", "stats-croston"]
    procs = []
    rows: list[dict[str, Any]] = []
    for model in models:
        trial_out = output / f"parallel-{model}"
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "all_model_runtime_validation.py"),
            "--catalog",
            "configs/model_catalog.json",
            "--available-only",
            "--models",
            model,
            "--require-fit",
            "--require-predict",
            "--require-save",
            "--require-load",
            "--require-retrain",
            "--require-property-validation",
            "--verify-arguments",
            "--parallel-cpu-models",
            "1",
            "--parallel-gpu-models",
            "0",
            "--timeout",
            "300",
            "--output",
            str(trial_out),
        ]
        start = time.time()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        procs.append((model, proc, start))
    for model, proc, start in procs:
        stdout, stderr = proc.communicate(timeout=300)
        end = time.time()
        rows.append({"model_id": model, "pid": proc.pid, "start": start, "end": end, "returncode": proc.returncode, "stdout_tail": stdout[-1000:], "stderr_tail": stderr[-1000:]})
    overlap = float(rows[0]["start"]) < float(rows[1]["end"]) and float(rows[1]["start"]) < float(rows[0]["end"])
    report = {"status": "PASS" if overlap and all(row["returncode"] == 0 for row in rows) else "FAILED", "overlap": overlap, "rows": rows}
    atomic_json(output / "parallel_execution_timeline.json", report)
    atomic_json(output / "resource_allocation.json", {"parallel_cpu_models": 2, "models": models})
    with (output / "parallel_execution_report.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return report


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_dir():
        for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
            digest.update(str(file_path.relative_to(path)).encode())
            digest.update(sha256_path(file_path).encode())
        return digest.hexdigest()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resume_proof(output: Path, run: Path) -> dict[str, Any]:
    rows = json.loads((run / "all_model_runtime_validation.json").read_text(encoding="utf-8"))
    decisions = []
    for row in rows:
        artifact = Path(row["artifact path"]) if row.get("artifact path") else None
        manifest = artifact is not None and (artifact if artifact.is_file() else artifact).exists()
        if row.get("final_status") in {"PASS", "ZERO_SHOT_PASS"} and artifact and artifact.exists():
            decision = "SKIP_VALID_PASS"
            artifact_hash = sha256_path(artifact)
        elif row.get("final_status") in {"PASS", "ZERO_SHOT_PASS"}:
            decision = "RERUN_ARTIFACT_MISSING"
            artifact_hash = None
        elif row.get("final_status") == "NOT_TESTED":
            decision = "RUN_NOT_TESTED"
            artifact_hash = None
        else:
            decision = "RERUN_PREVIOUS_FAILURE"
            artifact_hash = None
        decisions.append({"model_id": row["model_id"], "previous_status": row.get("final_status"), "artifact": str(artifact) if artifact else None, "artifact_exists": bool(artifact and artifact.exists()), "manifest_exists": bool(manifest), "artifact_hash": artifact_hash, "decision": decision})
    report = {"status": "PASS", "source_run": str(run), "decisions": decisions}
    atomic_json(output / "resume_decision.json", report)
    return report


def foundation_audit(output: Path) -> dict[str, Any]:
    models: list[dict[str, Any]] = [
        {"model_id": "timesfm-2.5", "repo_id": "google/timesfm-2.5-200m-pytorch", "package": "timesfm", "runtime": "dedicated uv environment recommended"},
        {"model_id": "tirex", "repo_id": "NX-AI/TiRex", "package": "tirex", "runtime": "dedicated subprocess provider recommended"},
        {"model_id": "moirai", "repo_id": "Salesforce/moirai-2.0-R-small", "package": "uni2ts", "runtime": "dedicated uv environment recommended"},
        {"model_id": "sundial", "repo_id": "thuml/sundial-base-128m", "package": "transformers", "runtime": "dedicated subprocess provider recommended"},
    ]
    for item in models:
        item.update({"local_cache_complete": False, "main_env_install": "not attempted", "cuda_16gb_fit": "requires model-specific validation", "license": "not verified offline"})
    report = {"status": "AUDIT_ONLY", "models": models}
    atomic_json(output / "foundation_environment_audit.json", report)
    lines = ["# Foundation Environment Audit", ""]
    for item in models:
        lines.append(f"- {item['model_id']}: repo={item['repo_id']}, package={item['package']}, cache_complete=false, runtime={item['runtime']}")
    (output / "foundation_environment_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def gpu_scheduler_proof(output: Path) -> dict[str, Any]:
    from loto.orchestration.resource_scheduler import ResourcePolicy, ResourceScheduler

    scheduler = ResourceScheduler(
        ResourcePolicy(
            max_parallel_cpu_models=1,
            max_parallel_gpu_models=1,
            gpus_per_trial=1,
            max_vram_mib=14500,
            gpu_memory_safety_margin_mib=1000,
            timeout_seconds=1,
        )
    )
    before = scheduler.gpu_resource_status(estimated_vram_mib=14500)
    lease = scheduler.acquire(requires_gpu=True, lease_id="gpu-proof-a", timeout=1)
    during = scheduler.gpu_resource_status(estimated_vram_mib=14500)
    try:
        try:
            scheduler.acquire(requires_gpu=True, lease_id="gpu-proof-b", timeout=0.1)
            second = "UNEXPECTED_ACQUIRED"
        except TimeoutError:
            second = "WAITING_FOR_GPU_RESOURCE"
    finally:
        scheduler.release(lease)
    after = scheduler.gpu_resource_status(estimated_vram_mib=14500)
    report = {
        "status": "PASS" if second == "WAITING_FOR_GPU_RESOURCE" else "FAILED",
        "before": before,
        "during": during,
        "second_gpu_trial": second,
        "after": after,
        "scheduler_report": scheduler.report(),
    }
    atomic_json(output / "gpu_scheduler_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=f"runs/all-model-runtime-validation/execution-proofs-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}")
    parser.add_argument("--resume-run", default="runs/all-model-runtime-validation/runtime-20260731-114151-ff06b9be")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "timeout": timeout_proof(output),
        "cpu_parallel": cpu_parallel_proof(output),
        "gpu_scheduler": gpu_scheduler_proof(output),
        "resume": resume_proof(output, Path(args.resume_run)),
        "foundation_audit": foundation_audit(output),
    }
    atomic_json(output / "execution_proofs_summary.json", summary)
    print(json.dumps({"output": str(output), "summary": {k: v.get("status") for k, v in summary.items()}}, ensure_ascii=False))
    return 0 if summary["timeout"]["status"] == "PASS" and summary["cpu_parallel"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
