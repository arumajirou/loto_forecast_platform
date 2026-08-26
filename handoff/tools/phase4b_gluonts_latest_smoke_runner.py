#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
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
EXPECTED_SOURCE_SHA = "8af95b2be18280589cbbb13aa1fc32dfb793767c"
ENV_NAME = "environments/gluonts-latest"
RUNTIME = ROOT / ENV_NAME / ".venv/bin/python"
SOURCE_PROVIDER = SOURCE_WT / ENV_NAME / "src"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
LOCAL_OUT = ROOT / "artifacts" / f"phase4b-gluonts-latest-smoke-{RUN_ID}"
CAMPAIGN_OUT = LOCAL_OUT / "campaign"
HANDOFF_OUT = HANDOFF / "phase4b"
EXPECTED_MODELS = (
    "DeepNPTSEstimator",
    "DeepAREstimator",
    "TiDEEstimator",
    "SimpleFeedForwardEstimator",
    "TemporalFusionTransformerEstimator",
    "WaveNetEstimator",
    "DLinearEstimator",
    "PatchTSTEstimator",
    "LagTSTEstimator",
)


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
    timeout: int = 60,
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
    proc = run(["git", "-C", str(HANDOFF_WT), *args], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def source_gate() -> None:
    proc = run(["git", "-C", str(SOURCE_WT), "rev-parse", "HEAD"])
    if proc.returncode != 0 or proc.stdout.strip() != EXPECTED_SOURCE_SHA:
        raise RuntimeError("SOURCE_SHA_GATE_FAILED")
    proc = run(["git", "-C", str(SOURCE_WT), "status", "--porcelain"])
    if proc.returncode != 0 or proc.stdout.strip():
        raise RuntimeError("SOURCE_WORKTREE_DIRTY")


def handoff_sync() -> None:
    if git_output(["branch", "--show-current"]) != BRANCH:
        raise RuntimeError("HANDOFF_BRANCH_GATE_FAILED")
    if git_output(["status", "--porcelain"]):
        raise RuntimeError("HANDOFF_WORKTREE_DIRTY")
    git_output(["fetch", "--prune", "origin"])
    proc = run(
        ["git", "-C", str(HANDOFF_WT), "pull", "--ff-only", "origin", BRANCH],
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"HANDOFF_PULL_FAILED: {proc.stderr.strip()}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def phase3d_gate() -> dict[str, str]:
    summary = json.loads((HANDOFF / "phase3d/summary.json").read_text(encoding="utf-8"))
    if summary.get("source_sha") != EXPECTED_SOURCE_SHA:
        raise RuntimeError("PHASE3D_SOURCE_SHA_MISMATCH")
    ready = read_tsv(HANDOFF / "phase3d/phase4-ready-queue.tsv")
    row = next((item for item in ready if item.get("environment") == ENV_NAME), None)
    if row is None:
        raise RuntimeError("GLUONTS_LATEST_NOT_IN_PHASE4_READY_QUEUE")
    if row.get("phase4_smoke_allowed") != "True":
        raise RuntimeError("GLUONTS_LATEST_PHASE4_SMOKE_NOT_ALLOWED")
    return row


def phase4a_gate() -> dict[str, Any]:
    path = HANDOFF / "phase4a/summary.json"
    if not path.exists():
        raise RuntimeError("PHASE4A_SUMMARY_MISSING")
    summary = json.loads(path.read_text(encoding="utf-8"))
    if summary.get("status") != "VERIFIED":
        raise RuntimeError("PHASE4A_NOT_VERIFIED")
    if summary.get("source_sha") not in (None, EXPECTED_SOURCE_SHA):
        raise RuntimeError("PHASE4A_SOURCE_SHA_MISMATCH")
    return summary


def runtime_probe() -> dict[str, Any]:
    if not RUNTIME.exists() or not os.access(RUNTIME, os.X_OK):
        raise RuntimeError(f"GLUONTS_LATEST_RUNTIME_MISSING: {RUNTIME}")
    code = r'''
import importlib.metadata, json, platform, sys
import gluonts
import torch

def version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None

print(json.dumps({
    "python": platform.python_version(),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "gluonts": version("gluonts"),
    "torch": version("torch"),
    "lightning": version("lightning"),
    "pytorch_lightning": version("pytorch-lightning"),
    "torch_cuda_build": str(torch.version.cuda),
    "torch_cuda_available_outside_provider": bool(torch.cuda.is_available()),
    "torch_device_count_outside_provider": int(torch.cuda.device_count()),
    "torch_device_name_outside_provider": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "compute_capability_outside_provider": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
    "arch_list": list(torch.cuda.get_arch_list()) if hasattr(torch.cuda, "get_arch_list") else [],
}, sort_keys=True))
'''
    proc = run([str(RUNTIME), "-I", "-c", code], timeout=60)
    (LOCAL_OUT / "runtime-probe.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "runtime-probe.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"GLUONTS_LATEST_RUNTIME_PROBE_FAILED: {proc.stderr.strip()}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if payload.get("gluonts") != "0.17.0":
        raise RuntimeError(f"GLUONTS_VERSION_MISMATCH: {payload.get('gluonts')}")
    return payload


def provider_registry_probe(env: dict[str, str]) -> dict[str, Any]:
    proc = run(
        [str(RUNTIME), "-m", "loto_gluonts_provider.p6_provider", "--registry"],
        timeout=60,
        env=env,
    )
    (LOCAL_OUT / "provider-registry.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "provider-registry.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"P6_PROVIDER_REGISTRY_FAILED: {proc.stderr.strip()}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    names = tuple(model["model_class"] for model in payload.get("models", []))
    if names != EXPECTED_MODELS:
        raise RuntimeError(f"P6_PROVIDER_REGISTRY_MODEL_MISMATCH: {names}")
    return payload


def run_campaign(env: dict[str, str]) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    CAMPAIGN_OUT.mkdir(parents=True, exist_ok=True)
    provider_command = f"{RUNTIME} -m loto_gluonts_provider.p6_provider"
    cmd = [
        str(RUNTIME),
        "-m",
        "loto.adapters.gluonts.p6_campaign_cli",
        "--run-id",
        f"phase4b-gluonts-latest-{RUN_ID}",
        "--lane",
        "latest",
        "--provider-command",
        provider_command,
        "--artifact-root",
        str(CAMPAIGN_OUT),
        "--workers",
        "1",
        "--timeout-seconds",
        "600",
    ]
    proc = run(cmd, timeout=7200, env=env)
    (LOCAL_OUT / "campaign.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (LOCAL_OUT / "campaign.stderr.log").write_text(proc.stderr, encoding="utf-8")
    result_path = CAMPAIGN_OUT / "p6_campaign_result.json"
    if not result_path.exists():
        raise RuntimeError(
            f"P6_CAMPAIGN_RESULT_MISSING: rc={proc.returncode} stderr={proc.stderr[-2000:]}"
        )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    return result, proc


def validate_campaign(result: dict[str, Any], proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    models = result.get("models") or []
    names = tuple(item.get("model_class") for item in models)
    if names != EXPECTED_MODELS:
        raise RuntimeError(f"P6_CAMPAIGN_MODEL_SET_MISMATCH: {names}")

    validation: dict[str, Any] = {
        "campaign_returncode_zero": proc.returncode == 0,
        "campaign_status_verified": result.get("status") == "VERIFIED",
        "nine_models_present": len(models) == 9,
        "all_model_statuses_verified": all(item.get("status") == "VERIFIED" for item in models),
        "fit_reload_present_all": True,
        "fit_required_checks_pass_all": True,
        "reload_required_checks_pass_all": True,
        "provider_cpu_device_pass_all": True,
        "separate_process_reload_all": True,
    }
    model_rows: list[dict[str, Any]] = []
    for item in models:
        fit_response = item.get("fit") or {}
        reload_response = item.get("reload") or {}
        fit = fit_response.get("evidence") or {}
        reload = reload_response.get("evidence") or {}
        fit_checks = fit.get("checks") or {}
        reload_checks = reload.get("checks") or {}
        validation["fit_reload_present_all"] &= bool(fit and reload)
        validation["fit_required_checks_pass_all"] &= bool(fit_checks) and all(
            value == "PASS" for value in fit_checks.values()
        )
        validation["reload_required_checks_pass_all"] &= bool(reload_checks) and all(
            value == "PASS" for value in reload_checks.values()
        )
        validation["provider_cpu_device_pass_all"] &= (
            fit_checks.get("device") == "PASS" and reload_checks.get("device") == "PASS"
        )
        fit_pid = fit.get("process_id")
        reload_pid = reload.get("process_id")
        validation["separate_process_reload_all"] &= bool(
            fit_pid and reload_pid and int(fit_pid) != int(reload_pid)
        )
        model_rows.append(
            {
                "model_class": item.get("model_class"),
                "status": item.get("status"),
                "fit_process_id": fit_pid,
                "reload_process_id": reload_pid,
                "fit_checks": fit_checks,
                "reload_checks": reload_checks,
                "errors": item.get("errors") or [],
            }
        )
    validation["all_critical_checks_pass"] = all(validation.values())
    return {"checks": validation, "models": model_rows}


def safe_publish(summary: dict[str, Any]) -> str:
    if HANDOFF_OUT.exists():
        shutil.rmtree(HANDOFF_OUT)
    HANDOFF_OUT.mkdir(parents=True, exist_ok=True)

    # Never publish predictor binaries. Retain only contracts, responses, logs,
    # manifests, hashes and summary evidence.
    for src in sorted(LOCAL_OUT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(LOCAL_OUT)
        if "predictors" in rel.parts:
            continue
        if src.suffix.lower() not in {".json", ".jsonl", ".md", ".log", ".txt", ".tsv"}:
            continue
        dst = HANDOFF_OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    dump_json(HANDOFF_OUT / "summary.json", summary)
    report = HANDOFF_OUT / "PHASE4B_REPORT.md"
    report.write_text(
        "\n".join(
            [
                "# Phase 4B — GluonTS latest P6 lifecycle smoke",
                "",
                f"- status: **{summary['status']}**",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                f"- runtime: `{RUNTIME}`",
                f"- GluonTS: `{summary['runtime'].get('gluonts')}`",
                f"- Torch: `{summary['runtime'].get('torch')}`",
                "- provider device policy: **CPU pinned** (`CUDA_VISIBLE_DEVICES` hidden by P6 campaign)",
                "- model count: **9**",
                "- lifecycle: FIT_SERIALIZE → separate-process LOAD_PREDICT",
                "- data: deterministic P6 certification fixture; **not an accuracy-ranking dataset**",
                "- final Hit@±1/MAE/MSE/RMSE comparison remains Phase 6 work",
                "",
                "## Critical checks",
                "",
                *[
                    f"- {key}: `{value}`"
                    for key, value in summary["validation"]["checks"].items()
                ],
                "",
                "## Models",
                "",
                *[
                    f"- `{row['model_class']}`: `{row['status']}` (fit pid={row['fit_process_id']}, reload pid={row['reload_process_id']})"
                    for row in summary["validation"]["models"]
                ],
                "",
                "## Interpretation",
                "",
                "This phase certifies the repository's current GluonTS P6 CPU contract on the existing latest runtime. Torch CUDA availability outside the provider process is provenance only and is not counted as GluonTS GPU execution.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    handoff_path = HANDOFF / "HANDOFF.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["handoff_run_id"] = RUN_ID
    handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    handoff.setdefault("completed_phases", {})["phase4b"] = summary["status"]
    handoff["current_phase"] = (
        "phase4b_gluonts_latest_verified_phase4c_next"
        if summary["status"] == "VERIFIED"
        else "phase4b_gluonts_latest_requires_review"
    )
    handoff["estimated_progress_percent"] = 48 if summary["status"] == "VERIFIED" else 44
    handoff["phase4b"] = summary
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
                f"- estimated progress: `{handoff['estimated_progress_percent']}%`",
                "- Phase 4A Darts GPU smoke: `VERIFIED`",
                f"- Phase 4B GluonTS latest P6 lifecycle: `{summary['status']}`",
                f"- source SHA: `{EXPECTED_SOURCE_SHA}`",
                "",
                "## Phase 4B",
                "",
                f"- runtime: `{RUNTIME}`",
                f"- GluonTS: `{summary['runtime'].get('gluonts')}`",
                "- P6 models: `9`",
                "- execution policy: `CPU pinned by repository P6 contract`",
                f"- all critical checks: `{summary['validation']['checks'].get('all_critical_checks_pass')}`",
                "- fixture: `deterministic certification series; non-ranking`",
                "",
                "## Next",
                "",
                "If VERIFIED, continue with `environments/gluonts-compat` using the same P6 contract. Do not treat installed CUDA as model GPU execution.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    file_sizes = HANDOFF / "FILE_SIZES.tsv"
    rows = []
    for path in HANDOFF.rglob("*"):
        if path.is_file():
            rows.append((path.stat().st_size, path))
    file_sizes.write_text(
        "".join(f"{size}\t{path}\n" for size, path in sorted(rows, reverse=True)),
        encoding="utf-8",
    )
    if any(size >= 95_000_000 for size, _ in rows):
        raise RuntimeError("HANDOFF_FILE_SIZE_GATE_FAILED")

    sums = HANDOFF / "SHA256SUMS"
    lines = []
    for path in sorted(HANDOFF.rglob("*")):
        if path.is_file() and path != sums:
            lines.append(f"{sha256_file(path)}  {path.relative_to(HANDOFF_WT)}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")

    add = run(["git", "-C", str(HANDOFF_WT), "add", "handoff"], timeout=60)
    if add.returncode != 0:
        raise RuntimeError(f"HANDOFF_ADD_FAILED: {add.stderr.strip()}")
    diff = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--quiet"], timeout=30)
    if diff.returncode not in (0, 1):
        raise RuntimeError(f"HANDOFF_DIFF_FAILED: {diff.stderr.strip()}")
    if diff.returncode == 1:
        commit = run(
            [
                "git",
                "-C",
                str(HANDOFF_WT),
                "commit",
                "-m",
                f"audit: publish Phase 4B GluonTS latest smoke {RUN_ID}",
            ],
            timeout=120,
        )
        if commit.returncode != 0:
            raise RuntimeError(f"HANDOFF_COMMIT_FAILED: {commit.stderr.strip()}")
    push = run(["git", "-C", str(HANDOFF_WT), "push", "origin", BRANCH], timeout=180)
    if push.returncode != 0:
        raise RuntimeError(f"HANDOFF_PUSH_FAILED: {push.stderr.strip()}")
    fetch = run(["git", "-C", str(HANDOFF_WT), "fetch", "origin", BRANCH], timeout=120)
    if fetch.returncode != 0:
        raise RuntimeError(f"HANDOFF_FETCH_FAILED: {fetch.stderr.strip()}")
    local = git_output(["rev-parse", "HEAD"])
    remote = git_output(["rev-parse", f"origin/{BRANCH}"])
    if local != remote:
        raise RuntimeError("HANDOFF_REMOTE_VERIFY_FAILED")
    return local


def main() -> int:
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)
    try:
        source_gate()
        handoff_sync()
        ready_row = phase3d_gate()
        phase4a = phase4a_gate()

        probe = runtime_probe()
        dump_json(LOCAL_OUT / "runtime-probe.json", probe)

        python_path = os.pathsep.join(
            [str(SOURCE_WT / "src"), str(SOURCE_PROVIDER), os.environ.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        child_env = {
            **os.environ,
            "PYTHONPATH": python_path,
            "PYTHONDONTWRITEBYTECODE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }

        registry = provider_registry_probe(child_env)
        dump_json(LOCAL_OUT / "provider-registry.json", registry)

        result, proc = run_campaign(child_env)
        validation = validate_campaign(result, proc)
        dump_json(LOCAL_OUT / "validation.json", validation)

        status = "VERIFIED" if validation["checks"]["all_critical_checks_pass"] else "FAILED"
        summary = {
            "schema_version": 1,
            "phase": "PHASE4B_GLUONTS_LATEST_P6_LIFECYCLE",
            "status": status,
            "run_id": RUN_ID,
            "source_sha": EXPECTED_SOURCE_SHA,
            "environment": ENV_NAME,
            "runtime_path": str(RUNTIME),
            "phase3d_ready_row": ready_row,
            "phase4a_status": phase4a.get("status"),
            "runtime": probe,
            "provider_registry_sha256": registry.get("registry_sha256"),
            "campaign_status": result.get("status"),
            "campaign_returncode": proc.returncode,
            "model_count": len(result.get("models") or []),
            "device_policy": {
                "requested_by_repository_p6": "cpu",
                "provider_cuda_visible_devices": "hidden by p6_campaign.invoke_p6_provider",
                "gpu_execution_claimed": False,
                "cpu_fallback": False,
                "reason": "GPU was not requested; CPU is the formal P6 contract",
            },
            "dataset_policy": {
                "kind": "deterministic_p6_certification_fixture",
                "real_lottery_data": False,
                "accuracy_ranking": False,
                "phase6_metrics_pending": [
                    "Hit@±1",
                    "MAE",
                    "MSE",
                    "RMSE",
                    "position_Hit@±1",
                    "all_position_Hit@±1",
                ],
            },
            "validation": validation,
            "local_artifact_root": str(LOCAL_OUT),
        }
        dump_json(LOCAL_OUT / "summary.json", summary)

        if status != "VERIFIED":
            print("============================================================")
            print("PHASE4B_GLUONTS_LATEST_SMOKE=FAILED")
            print(f"SUMMARY={LOCAL_OUT / 'summary.json'}")
            print(f"REPORT_PENDING={LOCAL_OUT}")
            print("============================================================")
            return 20

        head = safe_publish(summary)
        print("============================================================")
        print("PHASE4B_GLUONTS_LATEST_SMOKE=VERIFIED")
        print(f"HANDOFF_HEAD={head}")
        print(f"SUMMARY={HANDOFF_OUT / 'summary.json'}")
        print(f"REPORT={HANDOFF_OUT / 'PHASE4B_REPORT.md'}")
        print(
            "NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 4B結果を確認して次へ進めてください"
        )
        print("============================================================")
        return 0
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "phase": "PHASE4B_GLUONTS_LATEST_P6_LIFECYCLE",
            "status": "FAILED",
            "run_id": RUN_ID,
            "source_sha": EXPECTED_SOURCE_SHA,
            "environment": ENV_NAME,
            "error": f"{type(exc).__name__}: {exc}",
            "local_artifact_root": str(LOCAL_OUT),
        }
        dump_json(LOCAL_OUT / "summary.json", failure)
        print("============================================================")
        print("PHASE4B_GLUONTS_LATEST_SMOKE=FAILED")
        print(f"ERROR={type(exc).__name__}: {exc}")
        print(f"SUMMARY={LOCAL_OUT / 'summary.json'}")
        print("============================================================")
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
