from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from loto.probabilistic.kdpp_certification_gate import (
    APPROVAL_TOKEN,
    MODEL_ID,
    SCHEMA_VERSION,
    KDPPFormalVerificationReport,
    KDPPHistoryApproval,
    KDPPHistoryManifest,
    KDPPProcessRecord,
    sha256_file,
    tree_sha256,
    validate_history_bundle,
    validate_sha256,
    verify_runtime_directory,
    write_json,
)

SHA = "a" * 64
NOW = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "run_kdpp_fixed_k_target_host.py"


def inventory(root: Path, name: str, paths: list[Path]) -> None:
    (root / name).write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}\n" for path in sorted(paths)),
        encoding="utf-8",
    )


def manifest_payload(game: str = "miniloto", position: int | None = None) -> dict[str, object]:
    geometry = {
        "numbers3": ("position_local", 10, 1),
        "numbers4": ("position_local", 10, 1),
        "miniloto": ("unordered_fixed_cardinality", 31, 5),
        "loto6": ("unordered_fixed_cardinality", 43, 6),
        "loto7": ("unordered_fixed_cardinality", 37, 7),
    }[game]
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "bundle_status": "VERIFIED_REAL_HISTORY",
        "data_role": "TRAIN_ONLY",
        "game": game,
        "target_layout": geometry[0],
        "position": position,
        "source_system": "read-only-test-source",
        "source_snapshot": "snapshot-1",
        "source_query_sha256": SHA,
        "source_data_sha256": SHA,
        "created_at_utc": NOW.isoformat(),
        "train_start": 1,
        "train_end": 4,
        "forecast_origin": 5,
        "row_count": 4,
        "context_length": 4,
        "prediction_lengths": [1, 2, 5],
        "cardinality": geometry[2],
        "item_count": geometry[1],
        "training_npz_sha256": SHA,
        "item_ids_json_sha256": SHA,
        "read_only_source": True,
        "raw_data_immutable": True,
        "draw_order_verified": True,
        "future_actuals_included": False,
        "holdout_included": False,
        "prospective_included": False,
        "formal_approval_required": True,
    }


def approval_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "decision": "APPROVED",
        "approval_token": APPROVAL_TOKEN,
        "reviewer": "reviewer",
        "reviewed_at_utc": NOW.isoformat(),
        "history_manifest_sha256": SHA,
        "history_sha256sums_sha256": SHA,
        "source_read_only_confirmed": True,
        "train_only_confirmed": True,
        "draw_order_confirmed": True,
        "row_count_confirmed": True,
        "game_geometry_confirmed": True,
        "cutoff_confirmed": True,
        "no_future_actuals_confirmed": True,
        "no_holdout_confirmed": True,
        "no_prospective_confirmed": True,
    }


@pytest.mark.parametrize("game,position", [("numbers3", 1), ("numbers4", 4), ("miniloto", None), ("loto6", None), ("loto7", None)])
def test_manifest_geometry(game: str, position: int | None) -> None:
    manifest = KDPPHistoryManifest.model_validate(manifest_payload(game, position))
    assert manifest.game == game


def test_manifest_and_approval_are_strict() -> None:
    with pytest.raises(ValidationError):
        KDPPHistoryManifest.model_validate({**manifest_payload(), "unknown": 1})
    with pytest.raises(ValidationError):
        KDPPHistoryApproval.model_validate({**approval_payload(), "approval_token": "wrong"})
    with pytest.raises(ValueError):
        validate_sha256("A" * 64)


def build_history(root: Path) -> Path:
    root.mkdir()
    item_ids = [str(index) for index in range(1, 32)]
    (root / "item_ids.json").write_text(json.dumps(item_ids), encoding="utf-8")
    training = np.zeros((4, 31), dtype=np.int64)
    for row in range(4):
        training[row, row : row + 5] = 1
    np.savez_compressed(root / "training.npz", training_indicators=training, draw_nos=np.arange(1, 5))
    payload = manifest_payload()
    payload["training_npz_sha256"] = sha256_file(root / "training.npz")
    payload["item_ids_json_sha256"] = sha256_file(root / "item_ids.json")
    write_json(root / "history_manifest.json", payload)
    inventory(root, "SHA256SUMS", [root / "history_manifest.json", root / "item_ids.json", root / "training.npz"])
    return root


def build_approval(history: Path, path: Path) -> Path:
    payload = approval_payload()
    payload["history_manifest_sha256"] = sha256_file(history / "history_manifest.json")
    payload["history_sha256sums_sha256"] = sha256_file(history / "SHA256SUMS")
    write_json(path, payload)
    return path


def test_history_bundle_integrity_and_tamper(tmp_path: Path) -> None:
    history = build_history(tmp_path / "history")
    approval = build_approval(history, tmp_path / "approval.json")
    manifest, _, items = validate_history_bundle(history, approval)
    assert manifest.cardinality == 5 and len(items) == 31
    with (history / "item_ids.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="SHA-256"):
        validate_history_bundle(history, approval)


def test_draw_gap_is_rejected(tmp_path: Path) -> None:
    history = build_history(tmp_path / "history")
    with np.load(history / "training.npz") as arrays:
        training = arrays["training_indicators"]
    np.savez_compressed(history / "training.npz", training_indicators=training, draw_nos=np.array([1, 2, 4, 5]))
    payload = json.loads((history / "history_manifest.json").read_text())
    payload["training_npz_sha256"] = sha256_file(history / "training.npz")
    write_json(history / "history_manifest.json", payload)
    inventory(history, "SHA256SUMS", [history / "history_manifest.json", history / "item_ids.json", history / "training.npz"])
    approval = build_approval(history, tmp_path / "approval.json")
    with pytest.raises(ValueError, match="gap-free"):
        validate_history_bundle(history, approval)


def runtime_fixture(root: Path, pid: int = 123) -> Path:
    (root / "state").mkdir(parents=True)
    state_hash = "b" * 64
    prediction_hash = "c" * 64
    request = {"model_id": MODEL_ID, "actuals_used": False, "run_id": "run", "chronology_evidence": {"future_actuals_available": False}}
    response = {
        "model_id": MODEL_ID,
        "actuals_used": False,
        "run_id": "run",
        "requested_device": "cpu",
        "effective_device": "cpu",
        "cpu_fallback": False,
        "gpu_not_applicable": True,
        "gpu_uuid": None,
        "gpu_process_vram_mb": None,
        "quantiles": None,
        "finite_check": True,
        "exact_cardinality_check": True,
        "duplicate_check": True,
        "point_forecast_semantics": "SEEDED_EXACT_KDPP_SAMPLE",
        "runtime_pid": pid,
        "cardinality": 1,
        "prediction_length": 1,
        "point_forecast": [["n1:1"]],
        "marginal_inclusion_probabilities": [[0.1] * 10],
    }
    write_json(root / "request.json", request)
    write_json(root / "response.json", response)
    write_json(root / "prediction.lock.json", {"model_id": MODEL_ID, "actuals_used": False, "run_id": "run", "prediction_sha256": prediction_hash})
    write_json(root / "runtime_evidence.json", {"status": "PRIVATE_RUNTIME_EXECUTED", "runtime_pid": pid, "requested_device": "cpu", "effective_device": "cpu", "cpu_fallback": False, "gpu_not_applicable": True, "prediction_sha256": prediction_hash, "state_sha256": state_hash})
    write_json(root / "state/kdpp_state.json", {"state_sha256": state_hash})
    np.savez_compressed(root / "state/kdpp_state.npz", kernel=np.eye(10))
    write_json(root / "state/artifact_manifest.json", {"files": {}})
    inventory(root / "state", "SHA256SUMS", [root / "state/kdpp_state.json", root / "state/kdpp_state.npz", root / "state/artifact_manifest.json"])
    inventory(root, "CERTIFICATION_SHA256SUMS", [root / "state/kdpp_state.json", root / "state/kdpp_state.npz", root / "state/artifact_manifest.json", root / "state/SHA256SUMS", root / "request.json", root / "response.json", root / "prediction.lock.json", root / "runtime_evidence.json"])
    return root


def test_runtime_directory_and_tamper(tmp_path: Path) -> None:
    runtime = runtime_fixture(tmp_path / "runtime")
    result = verify_runtime_directory(runtime)
    assert result["runtime_pid"] == 123
    with (runtime / "response.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_runtime_directory(runtime)


def process_record(label: str, pid: int, prediction: str = "c" * 64) -> KDPPProcessRecord:
    return KDPPProcessRecord(
        label=label,
        external_pid=1,
        runtime_pid=pid,
        return_code=0,
        stdout_sha256=SHA,
        stderr_sha256=SHA,
        runtime_tree_sha256=SHA,
        state_sha256="b" * 64,
        prediction_sha256=prediction,
        prediction_seal_sha256=SHA,
        started_at_utc=NOW,
        completed_at_utc=NOW,
    )


def test_formal_report_cannot_fake_pass() -> None:
    gates = dict(
        approved_real_history_verified=True,
        train_only_verified=True,
        two_distinct_processes_verified=False,
        exact_prediction_replay_verified=True,
        exact_state_replay_verified=True,
        prediction_seals_verified=True,
        cpu_only_verified=True,
        no_actuals_verified=True,
        artifact_integrity_verified=True,
    )
    with pytest.raises(ValidationError):
        KDPPFormalVerificationReport(
            schema_version=SCHEMA_VERSION,
            model_id=MODEL_ID,
            status="PASS",
            certification_class="CPU_FORMAL",
            formal_runtime_certification=True,
            process_records=(process_record("A", 1), process_record("B", 2)),
            verified_at_utc=NOW,
            failure_codes=(),
            **gates,
        )


def fake_certifier(path: Path) -> Path:
    code = '''from __future__ import annotations
import argparse, json, os
from pathlib import Path
import numpy as np

def write(path, payload): path.write_text(json.dumps(payload, sort_keys=True)+"\\n")
def sha(path):
 import hashlib
 return hashlib.sha256(path.read_bytes()).hexdigest()
p=argparse.ArgumentParser()
for flag in ("training-npz","item-ids-json","output-dir","game","target-layout","train-start","train-end","forecast-origin","context-length","prediction-length","seed","source-revision","config-sha256","run-id","samples-per-horizon","rbf-gamma","quality-pseudocount","psd-tolerance"):
 p.add_argument("--"+flag, required=True)
a=p.parse_args(); root=Path(a.output_dir); state=root/"state"; state.mkdir(parents=True)
state_hash="b"*64; prediction_hash="c"*64; pid=os.getpid()
write(state/"kdpp_state.json", {"state_sha256":state_hash}); np.savez_compressed(state/"kdpp_state.npz", kernel=np.eye(10)); write(state/"artifact_manifest.json", {"files":{}})
(state/"SHA256SUMS").write_text("".join(f"{sha(state/n)}  {n}\\n" for n in ("artifact_manifest.json","kdpp_state.json","kdpp_state.npz")))
request={"model_id":"pp-k-dpp-fixed-k","actuals_used":False,"run_id":a.run_id,"chronology_evidence":{"future_actuals_available":False}}
response={"model_id":"pp-k-dpp-fixed-k","actuals_used":False,"run_id":a.run_id,"requested_device":"cpu","effective_device":"cpu","cpu_fallback":False,"gpu_not_applicable":True,"gpu_uuid":None,"gpu_process_vram_mb":None,"quantiles":None,"finite_check":True,"exact_cardinality_check":True,"duplicate_check":True,"point_forecast_semantics":"SEEDED_EXACT_KDPP_SAMPLE","runtime_pid":pid,"cardinality":1,"prediction_length":1,"point_forecast":[["n1:1"]],"marginal_inclusion_probabilities":[[0.1]*10]}
write(root/"request.json",request); write(root/"response.json",response); write(root/"prediction.lock.json",{"model_id":"pp-k-dpp-fixed-k","actuals_used":False,"run_id":a.run_id,"prediction_sha256":prediction_hash}); write(root/"runtime_evidence.json",{"status":"PRIVATE_RUNTIME_EXECUTED","runtime_pid":pid,"requested_device":"cpu","effective_device":"cpu","cpu_fallback":False,"gpu_not_applicable":True,"prediction_sha256":prediction_hash,"state_sha256":state_hash})
paths=[state/"kdpp_state.json",state/"kdpp_state.npz",state/"artifact_manifest.json",state/"SHA256SUMS",root/"request.json",root/"response.json",root/"prediction.lock.json",root/"runtime_evidence.json"]
(root/"CERTIFICATION_SHA256SUMS").write_text("".join(f"{sha(x)}  {x.relative_to(root).as_posix()}\\n" for x in sorted(paths)))
print(json.dumps({"status":"PRIVATE_RUNTIME_EXECUTED"}))
'''
    path.write_text(code, encoding="utf-8")
    return path


def test_full_prepare_run_verify_orchestration(tmp_path: Path) -> None:
    history = build_history(tmp_path / "history")
    # Position-local geometry makes the fake runtime cardinality consistent.
    item_ids = [f"n1:{digit}" for digit in range(10)]
    (history / "item_ids.json").write_text(json.dumps(item_ids), encoding="utf-8")
    training = np.zeros((4, 10), dtype=np.int64)
    training[np.arange(4), np.arange(4)] = 1
    np.savez_compressed(history / "training.npz", training_indicators=training, draw_nos=np.arange(1, 5))
    payload = manifest_payload("numbers3", 1)
    payload["training_npz_sha256"] = sha256_file(history / "training.npz")
    payload["item_ids_json_sha256"] = sha256_file(history / "item_ids.json")
    write_json(history / "history_manifest.json", payload)
    inventory(history, "SHA256SUMS", [history / "history_manifest.json", history / "item_ids.json", history / "training.npz"])
    approval = build_approval(history, tmp_path / "approval.json")
    certifier = fake_certifier(tmp_path / "fake_certifier.py")
    workspace = tmp_path / "workspace"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    base = [sys.executable, str(SCRIPT)]
    prepare = subprocess.run(base + ["prepare", "--history-bundle", str(history), "--history-approval", str(approval), "--certifier", str(certifier), "--workspace", str(workspace), "--run-id", "formal-1", "--source-revision", "d" * 40, "--config-sha256", "e" * 64, "--prediction-length", "1"], env=env, text=True, capture_output=True)
    assert prepare.returncode == 0, prepare.stderr
    run = subprocess.run(base + ["run", "--workspace", str(workspace)], env=env, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    verified = subprocess.run(base + ["verify", "--workspace", str(workspace)], env=env, text=True, capture_output=True)
    assert verified.returncode == 0, verified.stderr
    report = json.loads((workspace / "FORMAL_VERIFICATION_REPORT.json").read_text())
    assert report["certification_class"] == "CPU_FORMAL"
    assert report["formal_runtime_certification"] is True
    assert report["process_records"][0]["runtime_pid"] != report["process_records"][1]["runtime_pid"]


def test_tree_hash_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "tree"; root.mkdir()
    (root / "a").write_text("a"); (root / "b").write_text("b")
    assert tree_sha256(root) == tree_sha256(root)
