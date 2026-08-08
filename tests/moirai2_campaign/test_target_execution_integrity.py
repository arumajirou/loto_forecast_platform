from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loto.moirai2_campaign.target_execution import (
    CUDA_LANE,
    EVENT_ORDER,
    STAGES,
    SUPPORTED_LANE,
    TargetExecutionError,
    append_event,
    artifact_tree_sha256,
    build_initial_state,
    candidate_summary_for_lane,
    event_type_for,
    expected_next_event,
    load_json_object,
    sha256_file,
    validate_candidate_artifact,
    validate_installation_artifact,
    validate_state,
    verify_recorded_artifacts,
)


def _source_identity() -> dict[str, object]:
    return {
        "schema_version": "moirai2-source-identity-v1",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "worktree_clean": True,
        "changed_paths": [],
        "principal_file_sha256": {"source.py": "c" * 64},
    }


def _state(tmp_path: Path) -> dict[str, object]:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    return build_initial_state(
        run_id="p8d-test",
        snapshot_path=snapshot.resolve(),
        source_identity=_source_identity(),
        created_at="2026-08-06T00:00:00+00:00",
    )


def _artifact(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "evidence.txt").write_text(name + "\n", encoding="utf-8")
    return root


def _append(
    state: dict[str, object],
    tmp_path: Path,
    event_type: str,
    sequence: int,
) -> dict[str, object]:
    lane = None
    if event_type.startswith("supported_"):
        lane = SUPPORTED_LANE
    elif event_type.startswith("cuda_"):
        lane = CUDA_LANE
    return append_event(
        state,
        event_type=event_type,
        runtime_lane=lane,
        artifact_dir=_artifact(tmp_path, f"artifact-{sequence}"),
        summary={"sequence": sequence},
        recorded_at=f"2026-08-06T00:00:0{sequence}+00:00",
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _seal(root: Path) -> None:
    manifest = root / "SHA256SUMS"
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_artifact_tree_rejects_symlink(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    root.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("x\n", encoding="utf-8")
    (root / "link.txt").symlink_to(target)
    with pytest.raises(TargetExecutionError, match="symlink"):
        artifact_tree_sha256(root)


def test_state_timestamp_is_not_interpreted_as_approval(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert datetime.fromisoformat(state["created_at"]).tzinfo == timezone.utc
    assert state["stage"] == "INITIALIZED"


def test_candidate_unlisted_extra_file_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "candidate-extra"
    lock = root / "candidate-project" / "uv.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("version = 1\n", encoding="utf-8")
    _write_json(
        root / "CANDIDATE_RESULT.json",
        {
            "status": "PASS",
            "review_status": "PASS",
            "runtime_lane": SUPPORTED_LANE,
            "violation_count": 0,
            "candidate_lock_sha256": sha256_file(lock),
        },
    )
    _write_json(
        root / "LOCK_REVIEW_REPORT.json",
        {"status": "PASS", "runtime_lane": SUPPORTED_LANE},
    )
    _seal(root)
    (root / "unlisted.txt").write_text("extra\n", encoding="utf-8")
    with pytest.raises(TargetExecutionError, match="file set differs"):
        validate_candidate_artifact(root, runtime_lane=SUPPORTED_LANE)


def test_recorded_artifact_change_is_rejected(tmp_path: Path) -> None:
    state = _state(tmp_path)
    artifact = _artifact(tmp_path, "immutable-candidate")
    state = append_event(
        state,
        event_type=EVENT_ORDER[0],
        runtime_lane=SUPPORTED_LANE,
        artifact_dir=artifact,
        summary={"candidate_lock_sha256": "d" * 64},
        recorded_at="2026-08-06T00:00:01+00:00",
    )
    (artifact / "evidence.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(TargetExecutionError, match="artifact tree changed"):
        verify_recorded_artifacts(state)


def test_dry_run_installation_cannot_be_recorded(tmp_path: Path) -> None:
    root = tmp_path / "installation-ready"
    root.mkdir()
    lock_sha = "d" * 64
    _write_json(
        root / "INSTALLATION_EVIDENCE.json",
        {
            "status": "READY",
            "runtime_lane": SUPPORTED_LANE,
            "apply_requested": False,
            "candidate_lock_sha256": lock_sha,
            "reviewer": "operator",
            "reviewed_at": "2026-08-06T09:00:00+09:00",
            "installed_review": {
                "runtime_lane": SUPPORTED_LANE,
                "lock_sha256": lock_sha,
            },
        },
    )
    _seal(root)
    with pytest.raises(TargetExecutionError, match="not installed"):
        validate_installation_artifact(
            root,
            runtime_lane=SUPPORTED_LANE,
            candidate_summary={"candidate_lock_sha256": lock_sha},
        )
