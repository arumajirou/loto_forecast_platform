from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from loto.moirai2_campaign.target_execution import (
    MANIFEST_FILENAME,
    SHA_FILENAME,
    STATE_FILENAME,
    SUPPORTED_LANE,
    build_initial_state,
    load_json_object,
    validate_state,
    write_json_atomic,
)


ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_identity() -> dict[str, object]:
    return {
        "schema_version": "moirai2-source-identity-v1",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "worktree_clean": True,
        "changed_paths": [],
        "principal_file_sha256": {"source.py": "c" * 64},
    }


def test_prepare_script_contains_manual_approval_boundaries() -> None:
    text = (ROOT / "scripts" / "prepare_moirai2_target_execution.py").read_text(encoding="utf-8")
    assert "human_approval_required" in text
    assert '"automatic_approval": False' in text
    assert "SUPPORTED_REVIEWER" in text
    assert "SUPPORTED_REVIEWED_AT" in text
    assert "CUDA_REVIEWER" in text
    assert "CUDA_REVIEWED_AT" in text
    assert "APPLY-REVIEWED-MOIRAI2-LOCK" in text
    assert "workspace must be outside the Git repository" in text


def test_prepare_commands_are_sequential_and_end_with_pair_verification() -> None:
    module = _load_script("prepare_moirai2_target_execution.py")
    plan = {
        "run_id": "run",
        "snapshot_path": "/snapshot",
        "source_identity": {"commit_sha": "a" * 40},
        "artifact_paths": {
            "supported_candidate": "/a",
            "supported_dry_run": "/b",
            "supported_installation": "/c",
            "supported_campaign": "/d",
            "cuda_candidate": "/e",
            "cuda_dry_run": "/f",
            "cuda_installation": "/g",
            "cuda_campaign": "/h",
            "pair_verification": "/i",
        },
    }
    commands = module._commands(plan, Path("/control"))
    assert commands.index("supported-py311") < commands.index("cuda13-experimental")
    assert commands.rindex("verify_moirai2_runtime_evidence.py") < commands.rindex(
        "record-verification"
    )
    assert "Enterキーで終了します" in commands


def test_record_operation_creates_checkpoint_and_updates_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script("record_moirai2_target_execution.py")
    control = tmp_path / "control"
    control.mkdir()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    state = build_initial_state(
        run_id="run",
        snapshot_path=snapshot.resolve(),
        source_identity=_source_identity(),
        created_at="2026-08-06T00:00:00+00:00",
    )
    write_json_atomic(control / STATE_FILENAME, state)
    module._write_control_manifest(control)
    artifact = tmp_path / "candidate"
    artifact.mkdir()
    (artifact / "evidence.txt").write_text("candidate\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "validate_candidate_artifact",
        lambda artifact_dir, runtime_lane: {
            "runtime_lane": runtime_lane,
            "candidate_lock_sha256": "d" * 64,
        },
    )
    updated = module._record(
        control_dir=control,
        kind="candidate",
        runtime_lane=SUPPORTED_LANE,
        artifact_dir=artifact,
    )
    validate_state(updated)
    assert updated["stage"] == "SUPPORTED_CANDIDATE_RECORDED"
    checkpoints = list((control / "checkpoints").glob("*.json"))
    assert len(checkpoints) == 1
    assert (control / MANIFEST_FILENAME).is_file()
    assert (control / SHA_FILENAME).is_file()
    persisted = load_json_object(control / STATE_FILENAME)
    assert persisted["state_payload_sha256"] == updated["state_payload_sha256"]


def test_lock_file_prevents_concurrent_record(tmp_path: Path) -> None:
    module = _load_script("record_moirai2_target_execution.py")
    control = tmp_path / "control"
    control.mkdir()
    lock = module._acquire_lock(control)
    try:
        with pytest.raises(Exception, match="another record operation"):
            module._acquire_lock(control)
    finally:
        lock.unlink()


def test_record_script_does_not_contain_auto_approval() -> None:
    text = (ROOT / "scripts" / "record_moirai2_target_execution.py").read_text(encoding="utf-8")
    assert "APPLY-REVIEWED-MOIRAI2-LOCK" not in text
    assert "install_reviewed_moirai2_lock.py" not in text
    assert "subprocess.run" not in text


def test_control_tampering_blocks_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script("record_moirai2_target_execution.py")
    control = tmp_path / "control-tamper"
    control.mkdir()
    snapshot = tmp_path / "snapshot-tamper"
    snapshot.mkdir()
    state = build_initial_state(
        run_id="run",
        snapshot_path=snapshot.resolve(),
        source_identity=_source_identity(),
        created_at="2026-08-06T00:00:00+00:00",
    )
    write_json_atomic(control / STATE_FILENAME, state)
    module._write_control_manifest(control)
    (control / STATE_FILENAME).write_text("{}\n", encoding="utf-8")
    artifact = tmp_path / "candidate-tamper"
    artifact.mkdir()
    (artifact / "evidence.txt").write_text("candidate\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "validate_candidate_artifact",
        lambda artifact_dir, runtime_lane: {
            "runtime_lane": runtime_lane,
            "candidate_lock_sha256": "d" * 64,
        },
    )
    with pytest.raises(Exception, match="SHA-256 mismatch"):
        module._record(
            control_dir=control,
            kind="candidate",
            runtime_lane=SUPPORTED_LANE,
            artifact_dir=artifact,
        )


def test_full_record_sequence_opens_p9_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script("record_moirai2_target_execution.py")
    control = tmp_path / "control-full"
    control.mkdir()
    snapshot = tmp_path / "snapshot-full"
    snapshot.mkdir()
    state = build_initial_state(
        run_id="run-full",
        snapshot_path=snapshot.resolve(),
        source_identity=_source_identity(),
        created_at="2026-08-06T00:00:00+00:00",
    )
    write_json_atomic(control / STATE_FILENAME, state)
    module._write_control_manifest(control)

    def make_artifact(name: str) -> Path:
        root = tmp_path / name
        root.mkdir()
        (root / "evidence.txt").write_text(name + "\n", encoding="utf-8")
        return root

    monkeypatch.setattr(
        module,
        "validate_candidate_artifact",
        lambda artifact_dir, runtime_lane: {
            "runtime_lane": runtime_lane,
            "candidate_lock_sha256": ("d" * 64 if runtime_lane == SUPPORTED_LANE else "e" * 64),
        },
    )
    monkeypatch.setattr(
        module,
        "validate_installation_artifact",
        lambda artifact_dir, runtime_lane, candidate_summary: {
            "runtime_lane": runtime_lane,
            "candidate_lock_sha256": candidate_summary["candidate_lock_sha256"],
            "reviewer": "operator",
        },
    )
    monkeypatch.setattr(
        module,
        "validate_campaign_artifact",
        lambda artifact_dir, runtime_lane, source_commit: {
            "runtime_lane": runtime_lane,
            "source_commit": source_commit,
            "case_count": 6,
            "provider_process_count": 12,
        },
    )
    monkeypatch.setattr(
        module,
        "validate_pair_artifact",
        lambda artifact_dir, **kwargs: {
            "formal_campaign_count": 2,
            "formal_case_count": 12,
            "provider_process_evidence_count": 24,
            "p9_oof_gate_open": True,
        },
    )

    steps = (
        ("candidate", SUPPORTED_LANE, "supported-candidate"),
        ("installation", SUPPORTED_LANE, "supported-installation"),
        ("campaign", SUPPORTED_LANE, "supported-campaign"),
        ("candidate", "cuda13-experimental", "cuda-candidate"),
        ("installation", "cuda13-experimental", "cuda-installation"),
        ("campaign", "cuda13-experimental", "cuda-campaign"),
        ("verification", None, "pair-verification"),
    )
    updated = state
    for kind, lane, name in steps:
        updated = module._record(
            control_dir=control,
            kind=kind,
            runtime_lane=lane,
            artifact_dir=make_artifact(name),
        )
    validate_state(updated)
    assert updated["stage"] == "PAIR_VERIFIED"
    assert updated["p9_oof_gate_open"] is True
    assert len(list((control / "checkpoints").glob("*.json"))) == 7
