from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.moirai2_campaign.target_execution import (
    CUDA_LANE,
    EVENT_ORDER,
    STAGES,
    SUPPORTED_LANE,
    TargetExecutionError,
    append_event,
    build_initial_state,
    expected_next_event,
    sha256_file,
    validate_state,
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


def test_initial_state_is_closed() -> None:
    snapshot = Path("/tmp/snapshot")
    state = build_initial_state(
        run_id="run",
        snapshot_path=snapshot,
        source_identity=_source_identity(),
        created_at="2026-08-06T00:00:00+00:00",
    )
    validate_state(state)
    assert state["stage"] == "INITIALIZED"
    assert state["p9_oof_gate_open"] is False
    assert expected_next_event(state) == EVENT_ORDER[0]


def test_all_events_open_p9_only_at_last_event(tmp_path: Path) -> None:
    state = _state(tmp_path)
    for index, event_type in enumerate(EVENT_ORDER, start=1):
        state = _append(state, tmp_path, event_type, index)
        assert state["stage"] == STAGES[index]
        assert state["p9_oof_gate_open"] is (index == len(EVENT_ORDER))
    validate_state(state)
    assert expected_next_event(state) is None


def test_out_of_order_transition_is_rejected(tmp_path: Path) -> None:
    state = _state(tmp_path)
    with pytest.raises(TargetExecutionError, match="invalid transition"):
        _append(state, tmp_path, EVENT_ORDER[1], 1)


def test_event_hash_tampering_is_rejected(tmp_path: Path) -> None:
    state = _append(_state(tmp_path), tmp_path, EVENT_ORDER[0], 1)
    state["events"][0]["summary"]["sequence"] = 999
    with pytest.raises(TargetExecutionError, match="payload SHA-256|event SHA-256"):
        validate_state(state)


def test_dirty_source_is_rejected(tmp_path: Path) -> None:
    source = _source_identity()
    source["worktree_clean"] = False
    with pytest.raises(TargetExecutionError, match="worktree"):
        build_initial_state(
            run_id="run",
            snapshot_path=(tmp_path / "snapshot").resolve(),
            source_identity=source,
            created_at="2026-08-06T00:00:00+00:00",
        )


def test_relative_snapshot_is_rejected() -> None:
    with pytest.raises(TargetExecutionError, match="absolute"):
        build_initial_state(
            run_id="run",
            snapshot_path=Path("snapshot"),
            source_identity=_source_identity(),
            created_at="2026-08-06T00:00:00+00:00",
        )
