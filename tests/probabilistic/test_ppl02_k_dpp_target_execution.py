from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import loto.probabilistic.kdpp_target_event_validation as target_validation
import loto.probabilistic.kdpp_target_execution as target
from loto.probabilistic.kdpp_certification_gate import sha256_file

TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from kdpp_target_execution_support import (  # noqa: E402
    SHA,
    _approved_bundle,
    _prepared,
    _raw_handoff,
    _repository,
    _write_json,
)


def test_prepare_binds_two_clean_worktrees_and_commands(tmp_path: Path) -> None:
    workspace, _, _ = _prepared(tmp_path)
    plan = json.loads((workspace / "PLAN.json").read_text(encoding="utf-8"))
    commands = json.loads((workspace / "COMMANDS.json").read_text(encoding="utf-8"))
    assert plan["holdout_opened"] is False
    assert plan["prospective_opened"] is False
    assert plan["automatic_approval"] is False
    assert commands["database_credentials_embedded"] is False
    assert len(commands["commands"]) == 14
    assert target.verify_control_workspace(workspace).current_stage == "PREPARED"


def test_prepare_rejects_dirty_repository(tmp_path: Path) -> None:
    exporter, exporter_head = _repository(tmp_path / "exporter", target._EXPORTER_FILES)
    kdpp, kdpp_head = _repository(tmp_path / "kdpp", target._KDPP_FILES)
    (exporter / "untracked.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(ValueError, match="clean"):
        target.prepare_workspace(
            exporter_repo=exporter,
            exporter_head=exporter_head,
            exporter_python=Path(sys.executable),
            kdpp_repo=kdpp,
            kdpp_head=kdpp_head,
            kdpp_python=Path(sys.executable),
            workspace=tmp_path / "control",
            run_id="run",
            game="loto7",
            position=None,
            prediction_length=1,
            config_sha256=SHA,
        )


def test_stage_order_fails_closed(tmp_path: Path) -> None:
    workspace, _, _ = _prepared(tmp_path)
    raw = _raw_handoff(tmp_path / "raw")
    bundle, approved = _approved_bundle(raw, tmp_path)
    with pytest.raises(ValueError, match="expected next stage"):
        target.record_kdpp_history(workspace, bundle, approved)


def test_source_and_history_events_are_chained(tmp_path: Path) -> None:
    workspace, _, _ = _prepared(tmp_path)
    raw = _raw_handoff(tmp_path / "raw")
    source_event = target.record_source_handoff(workspace, raw)
    bundle, approved = _approved_bundle(raw, tmp_path)
    history_event = target.record_kdpp_history(workspace, bundle, approved)
    assert history_event.previous_event_sha256 == source_event.event_sha256
    state = target.verify_control_workspace(workspace)
    assert state.current_stage == "KDPP_HISTORY_RECORDED"
    assert state.event_count == 2


def test_prior_artifact_tamper_blocks_progress(tmp_path: Path) -> None:
    workspace, _, _ = _prepared(tmp_path)
    raw = _raw_handoff(tmp_path / "raw")
    target.record_source_handoff(workspace, raw)
    bundle, approved = _approved_bundle(raw, tmp_path)
    with (raw / "loto7.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="SHA-256"):
        target.record_kdpp_history(workspace, bundle, approved)


def test_event_payload_tamper_is_rejected(tmp_path: Path) -> None:
    workspace, _, _ = _prepared(tmp_path)
    raw = _raw_handoff(tmp_path / "raw")
    event = target.record_source_handoff(workspace, raw)
    path = target._event_path(workspace, 1, event.stage)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["summary"]["game_count"] = 4
    _write_json(path, payload)
    with pytest.raises(ValueError, match="event SHA-256"):
        target.verify_control_workspace(workspace)


def test_runtime_stage_requires_previous_artifacts_and_chains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _, _ = _prepared(tmp_path)
    raw = _raw_handoff(tmp_path / "raw")
    target.record_source_handoff(workspace, raw)
    bundle, approved = _approved_bundle(raw, tmp_path)
    target.record_kdpp_history(workspace, bundle, approved)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    report = runtime / "FORMAL_VERIFICATION_REPORT.json"
    report.write_text("{}\n", encoding="utf-8")

    def fake_validate(runtime_root: Path, *, plan: object) -> dict[str, object]:
        assert runtime_root == runtime.resolve()
        return {
            "certification_class": "CPU_FORMAL",
            "formal_runtime_certification": True,
            "game": "loto7",
            "position": None,
            "row_count": 8,
            "reviewer": "kdpp-reviewer",
            "runtime_pids": [101, 202],
            "prediction_sha256": "c" * 64,
            "state_sha256": "d" * 64,
            "report_sha256": sha256_file(report),
        }

    monkeypatch.setattr(target, "_validate_cpu_formal", fake_validate)
    monkeypatch.setattr(target_validation, "_validate_cpu_formal", fake_validate)
    event = target.record_cpu_formal(workspace, runtime)
    assert event.stage == "CPU_FORMAL_RECORDED"
    state = target.verify_control_workspace(workspace)
    assert state.current_stage == "CPU_FORMAL_RECORDED"
    assert state.event_count == 3
    final_report = workspace / "TARGET_EXECUTION_REPORT.json"
    payload = json.loads(final_report.read_text(encoding="utf-8"))
    assert payload["certification_class"] == "CPU_FORMAL"
    payload["oof_executed"] = True
    _write_json(final_report, payload)
    with pytest.raises(ValueError, match="report differs"):
        target.verify_control_workspace(workspace)


def test_missing_runtime_report_fails_closed(tmp_path: Path) -> None:
    workspace, _, _ = _prepared(tmp_path)
    plan = target._load_plan(workspace)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(FileNotFoundError):
        target._validate_cpu_formal(runtime, plan=plan)
