#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from loto.toto2_campaign.variant_probe import (
    VariantProbeError,
    is_wsl,
    load_json_object,
    parse_nvidia_compute_app_pids,
    query_gpu_compute_apps,
    query_gpu_uuid,
)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def require_native_linux() -> None:
    if sys.platform != "linux":
        raise VariantProbeError(f"native Linux required, got platform={sys.platform}")
    if is_wsl():
        raise VariantProbeError("native Linux required; WSL is not certification-capable")


def run_probe_process(
    *,
    probe_script: Path,
    output_dir: Path,
    cache_dir: Path,
    seed: int,
    local_files_only: bool,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(probe_script),
        "--output",
        str(output_dir),
        "--cache-dir",
        str(cache_dir),
        "--seed",
        str(seed),
    ]
    if local_files_only:
        command.append("--local-files-only")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    (output_dir.parent / f"{output_dir.name}.stdout.log").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (output_dir.parent / f"{output_dir.name}.stderr.log").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise VariantProbeError(
            f"probe process failed rc={completed.returncode}: {completed.stderr.strip()}"
        )
    return load_json_object(output_dir / "probe.json")


def certify_post_exit_release(*, probe: dict[str, Any], output_path: Path) -> dict[str, Any]:
    pid = int(probe["pid"])
    device = probe.get("device")
    if not isinstance(device, dict):
        raise VariantProbeError("probe device evidence is missing")
    if device.get("external_gpu_pid_captured") is not True:
        raise VariantProbeError("resident external GPU PID evidence is required")
    used_mib = int(device.get("nvidia_smi_used_gpu_memory_mib") or 0)
    if used_mib <= 0:
        raise VariantProbeError("resident external per-process VRAM must be positive")

    device_index = int(device.get("device_index", -1))
    if device_index < 0:
        raise VariantProbeError("resident CUDA device index is missing")
    execution_gpu_uuid = query_gpu_uuid(device_index)
    resident_gpu_uuid = str(device.get("gpu_uuid") or "")
    gpu_uuid_matches = resident_gpu_uuid == execution_gpu_uuid
    if not gpu_uuid_matches:
        raise VariantProbeError(
            "resident GPU UUID mismatch: "
            f"process={resident_gpu_uuid} execution={execution_gpu_uuid}"
        )

    process_exited = not Path(f"/proc/{pid}").exists()
    process_table = query_gpu_compute_apps()
    process_table_path = output_path.with_suffix(".nvidia-smi.csv")
    process_table_path.write_text(process_table, encoding="utf-8")
    observed_pids = sorted(parse_nvidia_compute_app_pids(process_table))
    external_pid_absent = pid not in observed_pids
    certified = process_exited and external_pid_absent
    payload = {
        "pid": pid,
        "process_exited": process_exited,
        "external_gpu_pid_absent": external_pid_absent,
        "post_exit_gpu_release_certified": certified,
        "observed_gpu_process_pids_after_exit": observed_pids,
        "resident_gpu_uuid": resident_gpu_uuid,
        "execution_gpu_uuid": execution_gpu_uuid,
        "gpu_uuid_matches_execution_device": gpu_uuid_matches,
        "resident_used_gpu_memory_mib": used_mib,
        "nvidia_smi_process_table_path": str(process_table_path),
    }
    atomic_json(output_path, payload)
    if not certified:
        raise VariantProbeError(
            f"post-exit GPU release not certified for pid {pid}: "
            f"process_exited={process_exited} external_pid_absent={external_pid_absent}"
        )
    return payload


def build_certification(
    *,
    first: dict[str, Any],
    second: dict[str, Any],
    release_1: dict[str, Any],
    release_2: dict[str, Any],
    output_1: np.ndarray,
    output_2: np.ndarray,
) -> dict[str, Any]:
    for index, probe in enumerate((first, second), start=1):
        if probe.get("status") != "PASS":
            raise VariantProbeError(f"native probe {index} must be PASS")
        device = probe.get("device")
        if not isinstance(device, dict):
            raise VariantProbeError(f"native probe {index} device evidence missing")
        if device.get("external_gpu_pid_captured") is not True:
            raise VariantProbeError(f"native probe {index} external PID evidence missing")
        if int(device.get("nvidia_smi_used_gpu_memory_mib") or 0) <= 0:
            raise VariantProbeError(f"native probe {index} external VRAM must be positive")
        if device.get("cpu_fallback") is not False:
            raise VariantProbeError(f"native probe {index} CPU fallback detected")
        if probe.get("certification_blockers"):
            raise VariantProbeError(f"native probe {index} has certification blockers")

    first_pid = int(first["pid"])
    second_pid = int(second["pid"])
    if first_pid == second_pid:
        raise VariantProbeError("provider process PIDs must be distinct")
    if first["snapshot"]["files"] != second["snapshot"]["files"]:
        raise VariantProbeError("snapshot inventory differs between native probes")
    if first["model_identity"] != second["model_identity"]:
        raise VariantProbeError("model identity differs between native probes")
    if first["device"]["gpu_uuid"] != second["device"]["gpu_uuid"]:
        raise VariantProbeError("GPU UUID differs between native probes")
    if first["native_output_sha256"] != second["native_output_sha256"]:
        raise VariantProbeError("native output SHA-256 differs between probes")
    if not np.array_equal(output_1, output_2):
        raise VariantProbeError("native output arrays differ between probes")
    if release_1.get("post_exit_gpu_release_certified") is not True:
        raise VariantProbeError("provider process 1 post-exit GPU release not certified")
    if release_2.get("post_exit_gpu_release_certified") is not True:
        raise VariantProbeError("provider process 2 post-exit GPU release not certified")

    return {
        "status": "PASS",
        "contract": "toto2-22m-native-linux-runtime-certification-v1",
        "revision": first["revision"],
        "snapshot_files": first["snapshot"]["files"],
        "exact_parameter_count": first["model_identity"]["parameter_count"],
        "model_class": first["model_identity"]["model_class"],
        "patch_size": first["model_identity"]["patch_size"],
        "quantile_levels": first["model_identity"]["quantile_levels"],
        "gpu_uuid": first["device"]["gpu_uuid"],
        "process_ids": [first_pid, second_pid],
        "external_used_gpu_memory_mib": [
            first["device"]["nvidia_smi_used_gpu_memory_mib"],
            second["device"]["nvidia_smi_used_gpu_memory_mib"],
        ],
        "peak_vram_bytes": [
            first["device"]["peak_vram_bytes"],
            second["device"]["peak_vram_bytes"],
        ],
        "exact_replay": True,
        "provider_processes_exited": True,
        "external_gpu_pid_captured": True,
        "post_exit_gpu_release_certified": True,
        "formal_runtime_certified": True,
        "manifest_runtime_certified_update_allowed": True,
        "shared_routing_allowed": False,
        "accuracy_certified": False,
        "holdout_open": False,
        "prospective_open": False,
        "certification_blockers": [],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    require_native_linux()
    args.output.mkdir(parents=True, exist_ok=False)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    first = run_probe_process(
        probe_script=args.probe_script,
        output_dir=args.output / "run-1",
        cache_dir=args.cache_dir,
        seed=args.seed,
        local_files_only=False,
    )
    release_1 = certify_post_exit_release(
        probe=first,
        output_path=args.output / "release-1.json",
    )

    second = run_probe_process(
        probe_script=args.probe_script,
        output_dir=args.output / "run-2",
        cache_dir=args.cache_dir,
        seed=args.seed,
        local_files_only=True,
    )
    release_2 = certify_post_exit_release(
        probe=second,
        output_path=args.output / "release-2.json",
    )

    output_1 = np.load(args.output / "run-1/native_output.npy", allow_pickle=False)
    output_2 = np.load(args.output / "run-2/native_output.npy", allow_pickle=False)
    return build_certification(
        first=first,
        second=second,
        release_1=release_1,
        release_2=release_2,
        output_1=output_1,
        output_2=output_2,
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Certify pinned Toto 2.0 22M on a native Linux CUDA host"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--probe-script",
        type=Path,
        default=repo_root / "scripts/probe_toto2_22m_runtime.py",
    )
    args = parser.parse_args()

    try:
        result = run(args)
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        result = {
            "status": "FAILED",
            "contract": "toto2-22m-native-linux-runtime-certification-v1",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "formal_runtime_certified": False,
            "manifest_runtime_certified_update_allowed": False,
            "shared_routing_allowed": False,
            "accuracy_certified": False,
            "holdout_open": False,
            "prospective_open": False,
        }
        atomic_json(args.output / "CERTIFICATION.json", result)
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    atomic_json(args.output / "CERTIFICATION.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
