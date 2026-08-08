from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
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
    verify_runtime_directory,
    write_json,
)

SHA = "a" * 64
NOW = datetime(2026, 8, 6, 3, 0, tzinfo=UTC)
ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "run_kdpp_fixed_k_target_host.py"


def _inventory(root: Path, name: str, paths: list[Path]) -> None:
    (root / name).write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(root).as_posix()}\n" for path in sorted(paths)
        ),
        encoding="utf-8",
    )


def _manifest(game: str = "miniloto", position: int | None = None) -> dict[str, object]:
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


def _approval() -> dict[str, object]:
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


@pytest.mark.parametrize(
    ("game", "position"),
    [("numbers3", 1), ("numbers4", 4), ("miniloto", None), ("loto6", None), ("loto7", None)],
)
def test_manifest_geometry(game: str, position: int | None) -> None:
    assert KDPPHistoryManifest.model_validate(_manifest(game, position)).game == game


def test_contracts_are_strict_and_fail_closed() -> None:
    with pytest.raises(ValidationError):
        KDPPHistoryManifest.model_validate({**_manifest(), "unknown": 1})
    with pytest.raises(ValidationError):
        KDPPHistoryApproval.model_validate({**_approval(), "approval_token": "wrong"})


def _history(root: Path) -> tuple[Path, Path]:
    root.mkdir()
    item_ids = [str(index) for index in range(1, 32)]
    (root / "item_ids.json").write_text(json.dumps(item_ids), encoding="utf-8")
    training = np.zeros((4, 31), dtype=np.int64)
    for row in range(4):
        training[row, row : row + 5] = 1
    np.savez_compressed(
        root / "training.npz",
        training_indicators=training,
        draw_nos=np.arange(1, 5),
    )
    manifest = _manifest()
    manifest["training_npz_sha256"] = sha256_file(root / "training.npz")
    manifest["item_ids_json_sha256"] = sha256_file(root / "item_ids.json")
    write_json(root / "history_manifest.json", manifest)
    _inventory(
        root,
        "SHA256SUMS",
        [root / "history_manifest.json", root / "item_ids.json", root / "training.npz"],
    )
    approval = _approval()
    approval["history_manifest_sha256"] = sha256_file(root / "history_manifest.json")
    approval["history_sha256sums_sha256"] = sha256_file(root / "SHA256SUMS")
    approval_path = root.parent / "approval.json"
    write_json(approval_path, approval)
    return root, approval_path


def test_history_bundle_integrity_and_tamper(tmp_path: Path) -> None:
    history, approval = _history(tmp_path / "history")
    manifest, _, items = validate_history_bundle(history, approval)
    assert manifest.cardinality == 5 and len(items) == 31
    (history / "item_ids.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        validate_history_bundle(history, approval)


def test_draw_gap_is_rejected(tmp_path: Path) -> None:
    history, approval = _history(tmp_path / "history")
    with np.load(history / "training.npz") as arrays:
        training = arrays["training_indicators"]
    np.savez_compressed(
        history / "training.npz",
        training_indicators=training,
        draw_nos=[1, 2, 4, 5],
    )
    payload = json.loads((history / "history_manifest.json").read_text())
    payload["training_npz_sha256"] = sha256_file(history / "training.npz")
    write_json(history / "history_manifest.json", payload)
    _inventory(
        history,
        "SHA256SUMS",
        [history / "history_manifest.json", history / "item_ids.json", history / "training.npz"],
    )
    approval_payload = json.loads(approval.read_text())
    approval_payload["history_manifest_sha256"] = sha256_file(history / "history_manifest.json")
    approval_payload["history_sha256sums_sha256"] = sha256_file(history / "SHA256SUMS")
    write_json(approval, approval_payload)
    with pytest.raises(ValueError, match="gap-free"):
        validate_history_bundle(history, approval)


def _runtime(root: Path) -> Path:
    state = root / "state"
    state.mkdir(parents=True)
    state_hash = "b" * 64
    prediction_hash = "c" * 64
    write_json(state / "kdpp_state.json", {"state_sha256": state_hash})
    np.savez_compressed(state / "kdpp_state.npz", kernel=np.eye(10))
    write_json(state / "artifact_manifest.json", {"files": {}})
    _inventory(
        state,
        "SHA256SUMS",
        [state / "kdpp_state.json", state / "kdpp_state.npz", state / "artifact_manifest.json"],
    )
    write_json(
        root / "request.json",
        {
            "model_id": MODEL_ID,
            "actuals_used": False,
            "chronology_evidence": {"future_actuals_available": False},
        },
    )
    write_json(
        root / "response.json",
        {
            "model_id": MODEL_ID,
            "actuals_used": False,
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
            "runtime_pid": 123,
            "cardinality": 1,
            "point_forecast": [["n1:1"]],
            "marginal_inclusion_probabilities": [[0.1] * 10],
        },
    )
    write_json(
        root / "prediction.lock.json",
        {
            "model_id": MODEL_ID,
            "actuals_used": False,
            "prediction_sha256": prediction_hash,
        },
    )
    write_json(
        root / "runtime_evidence.json",
        {"runtime_pid": 123, "prediction_sha256": prediction_hash, "state_sha256": state_hash},
    )
    _inventory(
        root,
        "CERTIFICATION_SHA256SUMS",
        [
            state / "kdpp_state.json",
            state / "kdpp_state.npz",
            state / "artifact_manifest.json",
            state / "SHA256SUMS",
            root / "request.json",
            root / "response.json",
            root / "prediction.lock.json",
            root / "runtime_evidence.json",
        ],
    )
    return root


def test_runtime_directory_integrity_and_tamper(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "runtime")
    assert verify_runtime_directory(runtime)["runtime_pid"] == 123
    with (runtime / "response.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_runtime_directory(runtime)


def _record(label: str, pid: int) -> KDPPProcessRecord:
    return KDPPProcessRecord(
        label=label,
        external_pid=1,
        runtime_pid=pid,
        return_code=0,
        stdout_sha256=SHA,
        stderr_sha256=SHA,
        runtime_tree_sha256=SHA,
        state_sha256="b" * 64,
        prediction_sha256="c" * 64,
        prediction_seal_sha256=SHA,
        started_at_utc=NOW,
        completed_at_utc=NOW,
    )


def test_formal_report_cannot_fake_pass() -> None:
    gates = {
        "approved_real_history_verified": True,
        "train_only_verified": True,
        "two_distinct_processes_verified": False,
        "exact_prediction_replay_verified": True,
        "exact_state_replay_verified": True,
        "prediction_seals_verified": True,
        "cpu_only_verified": True,
        "no_actuals_verified": True,
        "artifact_integrity_verified": True,
    }
    with pytest.raises(ValidationError):
        KDPPFormalVerificationReport(
            schema_version=SCHEMA_VERSION,
            model_id=MODEL_ID,
            status="PASS",
            certification_class="CPU_FORMAL",
            formal_runtime_certification=True,
            process_records=(_record("A", 1), _record("B", 2)),
            verified_at_utc=NOW,
            **gates,
        )


def test_tree_hash_and_cli_help(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a").write_text("a")
    (root / "b").write_text("b")
    assert tree_sha256(root) == tree_sha256(root)
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], text=True, capture_output=True)
    assert result.returncode == 0
