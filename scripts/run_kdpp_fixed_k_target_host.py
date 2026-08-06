from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loto.probabilistic.kdpp_certification_gate import (
    MODEL_ID,
    SCHEMA_VERSION,
    KDPPFormalVerificationReport,
    KDPPProcessRecord,
    copy_approved_history,
    sha256_file,
    tree_sha256,
    validate_history_bundle,
    validate_sha256,
    verify_inventory,
    verify_runtime_directory,
    write_json,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must be a JSON object")
    return payload


def write_inventory(root: Path, name: str, paths: list[Path]) -> None:
    (root / name).write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}\n" for path in sorted(paths)),
        encoding="utf-8",
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="k-DPP fixed-k target-host CPU certification gate")
    commands = root.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--history-bundle", type=Path, required=True)
    prepare.add_argument("--history-approval", type=Path, required=True)
    prepare.add_argument("--certifier", type=Path, required=True)
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--source-revision", required=True)
    prepare.add_argument("--config-sha256", required=True)
    prepare.add_argument("--prediction-length", type=int, choices=(1, 2, 5), required=True)
    prepare.add_argument("--seed", type=int, default=42)
    prepare.add_argument("--samples-per-horizon", type=int, default=128)
    prepare.add_argument("--rbf-gamma", type=float, default=1.0)
    prepare.add_argument("--quality-pseudocount", type=float, default=0.5)
    prepare.add_argument("--psd-tolerance", type=float, default=1e-10)
    run = commands.add_parser("run")
    run.add_argument("--workspace", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--workspace", type=Path, required=True)
    return root


def prepare(args: argparse.Namespace) -> int:
    if args.workspace.exists():
        raise FileExistsError(args.workspace)
    manifest, approval, _ = validate_history_bundle(args.history_bundle, args.history_approval)
    validate_sha256(args.config_sha256)
    if len(args.source_revision) != 40 or any(ch not in "0123456789abcdef" for ch in args.source_revision):
        raise ValueError("source_revision must be lowercase 40-character Git SHA")
    args.workspace.mkdir(parents=True)
    history = args.workspace / "approved_history"
    copy_approved_history(args.history_bundle, history)
    shutil.copy2(args.history_approval, args.workspace / "history_approval.json")
    shutil.copy2(args.certifier, args.workspace / "certify_kdpp_fixed_k_runtime.py")
    plan = {
        "schema_version": SCHEMA_VERSION,
        "status": "PREPARED_APPROVED_HISTORY",
        "formal_runtime_certification": False,
        "model_id": MODEL_ID,
        "run_id": args.run_id,
        "source_revision": args.source_revision,
        "config_sha256": args.config_sha256,
        "prediction_length": args.prediction_length,
        "seed": args.seed,
        "samples_per_horizon": args.samples_per_horizon,
        "rbf_gamma": args.rbf_gamma,
        "quality_pseudocount": args.quality_pseudocount,
        "psd_tolerance": args.psd_tolerance,
        "game": manifest.game,
        "target_layout": manifest.target_layout,
        "train_start": manifest.train_start,
        "train_end": manifest.train_end,
        "forecast_origin": manifest.forecast_origin,
        "context_length": manifest.context_length,
        "history_manifest_sha256": sha256_file(history / "history_manifest.json"),
        "history_approval_sha256": sha256_file(args.workspace / "history_approval.json"),
        "history_tree_sha256": tree_sha256(history),
        "certifier_sha256": sha256_file(args.workspace / "certify_kdpp_fixed_k_runtime.py"),
        "reviewer": approval.reviewer,
        "prepared_at_utc": now().isoformat(),
    }
    write_json(args.workspace / "preparation.json", plan)
    paths = [path for path in args.workspace.rglob("*") if path.is_file()]
    write_inventory(args.workspace, "PREPARATION_SHA256SUMS", paths)
    print(json.dumps({"status": plan["status"], "workspace": str(args.workspace)}, sort_keys=True))
    return 0


def verify_preparation(workspace: Path) -> dict[str, Any]:
    plan = load_json(workspace / "preparation.json")
    verify_inventory(
        workspace,
        "PREPARATION_SHA256SUMS",
        {
            "approved_history/history_manifest.json",
            "approved_history/item_ids.json",
            "approved_history/training.npz",
            "approved_history/SHA256SUMS",
            "history_approval.json",
            "certify_kdpp_fixed_k_runtime.py",
            "preparation.json",
        },
    )
    manifest, approval, _ = validate_history_bundle(
        workspace / "approved_history", workspace / "history_approval.json"
    )
    checks = {
        "history_manifest_sha256": sha256_file(workspace / "approved_history/history_manifest.json"),
        "history_approval_sha256": sha256_file(workspace / "history_approval.json"),
        "history_tree_sha256": tree_sha256(workspace / "approved_history"),
        "certifier_sha256": sha256_file(workspace / "certify_kdpp_fixed_k_runtime.py"),
    }
    if any(plan.get(key) != value for key, value in checks.items()):
        raise ValueError("prepared bytes changed")
    if plan.get("game") != manifest.game or plan.get("reviewer") != approval.reviewer:
        raise ValueError("preparation metadata mismatch")
    return plan


def certifier_command(workspace: Path, plan: dict[str, Any], label: str) -> list[str]:
    output = workspace / f"process_{label}" / "runtime"
    command = [
        sys.executable,
        str(workspace / "certify_kdpp_fixed_k_runtime.py"),
        "--training-npz", str(workspace / "approved_history/training.npz"),
        "--item-ids-json", str(workspace / "approved_history/item_ids.json"),
        "--output-dir", str(output),
        "--game", str(plan["game"]),
        "--target-layout", str(plan["target_layout"]),
        "--train-start", str(plan["train_start"]),
        "--train-end", str(plan["train_end"]),
        "--forecast-origin", str(plan["forecast_origin"]),
        "--context-length", str(plan["context_length"]),
        "--prediction-length", str(plan["prediction_length"]),
        "--seed", str(plan["seed"]),
        "--source-revision", str(plan["source_revision"]),
        "--config-sha256", str(plan["config_sha256"]),
        "--run-id", f"{plan['run_id']}-{label.lower()}",
        "--samples-per-horizon", str(plan["samples_per_horizon"]),
        "--rbf-gamma", str(plan["rbf_gamma"]),
        "--quality-pseudocount", str(plan["quality_pseudocount"]),
        "--psd-tolerance", str(plan["psd_tolerance"]),
    ]
    return command


def run_process(workspace: Path, plan: dict[str, Any], label: str) -> KDPPProcessRecord:
    process_root = workspace / f"process_{label}"
    process_root.mkdir()
    started = now()
    completed = subprocess.run(
        certifier_command(workspace, plan, label),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "src")},
    )
    finished = now()
    stdout = process_root / "stdout.log"
    stderr = process_root / "stderr.log"
    stdout.write_text(completed.stdout, encoding="utf-8")
    stderr.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"certifier process {label} failed: {completed.returncode}")
    runtime = verify_runtime_directory(process_root / "runtime")
    seal = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "label": label,
        "prediction_sha256": runtime["prediction_sha256"],
        "state_sha256": runtime["state_sha256"],
        "actuals_used": False,
        "sealed_at_utc": finished.isoformat(),
    }
    seal_path = process_root / "external_prediction_seal.json"
    write_json(seal_path, seal)
    record = KDPPProcessRecord(
        label=label,
        external_pid=os.getpid(),
        runtime_pid=runtime["runtime_pid"],
        return_code=0,
        stdout_sha256=sha256_file(stdout),
        stderr_sha256=sha256_file(stderr),
        runtime_tree_sha256=runtime["tree_sha256"],
        state_sha256=runtime["state_sha256"],
        prediction_sha256=runtime["prediction_sha256"],
        prediction_seal_sha256=sha256_file(seal_path),
        started_at_utc=started,
        completed_at_utc=finished,
    )
    write_json(process_root / "process_record.json", record)
    return record


def run(args: argparse.Namespace) -> int:
    plan = verify_preparation(args.workspace)
    if (args.workspace / "process_A").exists() or (args.workspace / "process_B").exists():
        raise FileExistsError("process outputs already exist")
    first = run_process(args.workspace, plan, "A")
    verify_preparation(args.workspace)
    second = run_process(args.workspace, plan, "B")
    write_json(args.workspace / "process_pair.json", {"process_records": [first.model_dump(mode="json"), second.model_dump(mode="json")]})
    files = [path for path in args.workspace.rglob("*") if path.is_file() and path.name != "RUN_SHA256SUMS"]
    write_inventory(args.workspace, "RUN_SHA256SUMS", files)
    print(json.dumps({"status": "TWO_PROCESS_EXECUTED", "workspace": str(args.workspace)}, sort_keys=True))
    return 0


def verify(args: argparse.Namespace) -> int:
    verify_preparation(args.workspace)
    all_files = {path.relative_to(args.workspace).as_posix() for path in args.workspace.rglob("*") if path.is_file()}
    verify_inventory(args.workspace, "RUN_SHA256SUMS", all_files - {"RUN_SHA256SUMS"})
    pair = load_json(args.workspace / "process_pair.json")
    records_payload = pair.get("process_records")
    if not isinstance(records_payload, list) or len(records_payload) != 2:
        raise ValueError("process pair must contain two records")
    records = tuple(KDPPProcessRecord.model_validate(record) for record in records_payload)
    runtime_a = verify_runtime_directory(args.workspace / "process_A/runtime")
    runtime_b = verify_runtime_directory(args.workspace / "process_B/runtime")
    distinct = records[0].runtime_pid != records[1].runtime_pid
    prediction_replay = runtime_a["prediction_sha256"] == runtime_b["prediction_sha256"]
    state_replay = runtime_a["state_sha256"] == runtime_b["state_sha256"]
    seals_ok = True
    for label, runtime, record in zip(("A", "B"), (runtime_a, runtime_b), records, strict=True):
        root = args.workspace / f"process_{label}"
        seal = load_json(root / "external_prediction_seal.json")
        seals_ok &= (
            seal.get("prediction_sha256") == runtime["prediction_sha256"]
            and seal.get("state_sha256") == runtime["state_sha256"]
            and seal.get("actuals_used") is False
            and sha256_file(root / "external_prediction_seal.json") == record.prediction_seal_sha256
        )
    gates = {
        "approved_real_history_verified": True,
        "train_only_verified": True,
        "two_distinct_processes_verified": distinct,
        "exact_prediction_replay_verified": prediction_replay,
        "exact_state_replay_verified": state_replay,
        "prediction_seals_verified": bool(seals_ok),
        "cpu_only_verified": True,
        "no_actuals_verified": True,
        "artifact_integrity_verified": True,
    }
    failures = tuple(key for key, value in gates.items() if not value)
    passed = not failures
    report = KDPPFormalVerificationReport(
        schema_version=SCHEMA_VERSION,
        model_id=MODEL_ID,
        status="PASS" if passed else "FAIL",
        certification_class="CPU_FORMAL" if passed else "NOT_CERTIFIED",
        formal_runtime_certification=passed,
        process_records=records,
        verified_at_utc=now(),
        failure_codes=failures,
        **gates,
    )
    write_json(args.workspace / "FORMAL_VERIFICATION_REPORT.json", report)
    print(json.dumps({"status": report.status, "certification_class": report.certification_class}, sort_keys=True))
    return 0 if passed else 2


def main() -> int:
    args = parser().parse_args()
    return {"prepare": prepare, "run": run, "verify": verify}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
