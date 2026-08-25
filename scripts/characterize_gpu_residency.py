#!/usr/bin/env python3
"""Characterize incremental GPU VRAM used by one operator-supplied foundation command."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gpu_snapshot(index: int) -> dict[str, Any]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,memory.used,memory.free,memory.total",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if len(fields) == 5 and int(fields[0]) == index:
            return {
                "index": index,
                "uuid": fields[1],
                "memory_used_mib": int(fields[2]),
                "memory_free_mib": int(fields[3]),
                "memory_total_mib": int(fields[4]),
            }
    raise RuntimeError(f"nvidia-smi did not report GPU index {index}")


def _gpu_processes(gpu_uuid: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if len(fields) != 4 or fields[0] != gpu_uuid:
            continue
        try:
            used = int(fields[3])
        except ValueError:
            used = None
        rows.append(
            {
                "gpu_uuid": fields[0],
                "pid": int(fields[1]),
                "process_name": fields[2],
                "used_memory_mib": used,
            }
        )
    return rows


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--interval-seconds", type=float, default=0.1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--llm-alias", required=True)
    parser.add_argument("--llm-runtime", required=True)
    parser.add_argument("--llm-context-length", type=int, required=True)
    parser.add_argument("--foundation-repo-id", required=True)
    parser.add_argument("--foundation-revision", required=True)
    parser.add_argument("--runtime-lane", required=True)
    parser.add_argument("--code-sha256")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.interval_seconds < 0.05:
        parser.error("--interval-seconds must be >= 0.05")
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def main() -> int:
    args = _parse_args()
    baseline = _gpu_snapshot(args.gpu_index)
    baseline_processes = _gpu_processes(baseline["uuid"])
    baseline_pids = sorted(int(row["pid"]) for row in baseline_processes)
    run_id = (
        "gpu-residency-characterize-"
        + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid4().hex[:8]
    )

    started_at_utc = datetime.now(UTC).isoformat()
    started = time.monotonic()
    proc = subprocess.Popen(args.command)
    peak_used = baseline["memory_used_mib"]
    samples = 0
    while proc.poll() is None:
        snap = _gpu_snapshot(args.gpu_index)
        peak_used = max(peak_used, snap["memory_used_mib"])
        samples += 1
        time.sleep(args.interval_seconds)
    return_code = int(proc.returncode or 0)

    final = _gpu_snapshot(args.gpu_index)
    final_processes = _gpu_processes(final["uuid"])
    final_pids = sorted(int(row["pid"]) for row in final_processes)
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at_utc": started_at_utc,
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "duration_seconds": time.monotonic() - started,
        "command": args.command,
        "command_exit_code": return_code,
        "gpu": {
            "uuid": baseline["uuid"],
            "index": baseline["index"],
            "memory_total_mib": baseline["memory_total_mib"],
            "baseline_used_mib": baseline["memory_used_mib"],
            "peak_used_mib": peak_used,
            "final_used_mib": final["memory_used_mib"],
        },
        "llm": {
            "alias": args.llm_alias,
            "runtime": args.llm_runtime,
            "context_length": args.llm_context_length,
            "baseline_gpu_pids": baseline_pids,
            "final_gpu_pids": final_pids,
            "baseline_process_names": sorted(
                {str(row["process_name"]) for row in baseline_processes}
            ),
        },
        "foundation": {
            "repo_id": args.foundation_repo_id,
            "revision": args.foundation_revision,
            "runtime_lane": args.runtime_lane,
        },
        "external_peak_vram_mib": max(
            0,
            int(peak_used) - int(baseline["memory_used_mib"]),
        ),
        "sample_count": samples,
        "code_sha256": args.code_sha256,
        "continuity": {
            "baseline_pid_set_equals_final": baseline_pids == final_pids,
            "gpu_uuid_stable": baseline["uuid"] == final["uuid"],
        },
    }
    if return_code != 0:
        payload["status"] = "FAILED"
        payload["failure"] = f"characterized command exited with {return_code}"
    elif payload["external_peak_vram_mib"] <= 0:
        payload["status"] = "FAILED"
        payload["failure"] = "no positive incremental external VRAM peak observed"
    elif baseline["uuid"] != final["uuid"]:
        payload["status"] = "FAILED"
        payload["failure"] = "GPU UUID changed during characterization"
    elif baseline_pids != final_pids:
        payload["status"] = "FAILED"
        payload["failure"] = "resident GPU PID set changed during characterization"
    else:
        payload["status"] = "PASS"
        payload["failure"] = None

    _write_json_atomic(args.output, payload)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{_sha256_file(args.output)}  {args.output.name}\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
