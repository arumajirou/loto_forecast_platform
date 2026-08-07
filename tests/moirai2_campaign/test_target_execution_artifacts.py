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
            lines.append(
                f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
            )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_candidate_validation_recomputes_lock_sha(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    lock = root / "candidate-project" / "uv.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("version = 1\n", encoding="utf-8")
    lock_sha = sha256_file(lock)
    _write_json(
        root / "CANDIDATE_RESULT.json",
        {
            "status": "PASS",
            "review_status": "PASS",
            "runtime_lane": SUPPORTED_LANE,
            "violation_count": 0,
            "warning_count": 1,
            "package_count": 10,
            "candidate_lock_sha256": lock_sha,
        },
    )
    _write_json(
        root / "LOCK_REVIEW_REPORT.json",
        {
            "status": "PASS",
            "runtime_lane": SUPPORTED_LANE,
        },
    )
    _seal(root)
    summary = validate_candidate_artifact(root, runtime_lane=SUPPORTED_LANE)
    assert summary["candidate_lock_sha256"] == lock_sha
    assert summary["manifest"]["entry_count"] == 3


def test_candidate_tampering_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
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
    lock.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(TargetExecutionError, match="SHA-256 mismatch"):
        validate_candidate_artifact(root, runtime_lane=SUPPORTED_LANE)


def test_installation_requires_human_review_and_applied_status(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir()
    lock_sha = "d" * 64
    _write_json(
        root / "INSTALLATION_EVIDENCE.json",
        {
            "status": "INSTALLED",
            "runtime_lane": SUPPORTED_LANE,
            "apply_requested": True,
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
    summary = validate_installation_artifact(
        root,
        runtime_lane=SUPPORTED_LANE,
        candidate_summary={"candidate_lock_sha256": lock_sha},
    )
    assert summary["reviewer"] == "operator"


def test_installation_without_timezone_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    root.mkdir()
    lock_sha = "d" * 64
    _write_json(
        root / "INSTALLATION_EVIDENCE.json",
        {
            "status": "INSTALLED",
            "runtime_lane": SUPPORTED_LANE,
            "apply_requested": True,
            "candidate_lock_sha256": lock_sha,
            "reviewer": "operator",
            "reviewed_at": "2026-08-06T09:00:00",
            "installed_review": {
                "runtime_lane": SUPPORTED_LANE,
                "lock_sha256": lock_sha,
            },
        },
    )
    _seal(root)
    with pytest.raises(TargetExecutionError, match="timezone-aware"):
        validate_installation_artifact(
            root,
            runtime_lane=SUPPORTED_LANE,
            candidate_summary={"candidate_lock_sha256": lock_sha},
        )


def test_candidate_summary_requires_recorded_lane(tmp_path: Path) -> None:
    state = _state(tmp_path)
    with pytest.raises(TargetExecutionError, match="not recorded"):
        candidate_summary_for_lane(state, SUPPORTED_LANE)


def test_event_type_mapping_is_explicit() -> None:
    assert event_type_for("candidate", SUPPORTED_LANE) == EVENT_ORDER[0]
    assert event_type_for("campaign", CUDA_LANE) == EVENT_ORDER[5]
    assert event_type_for("verification", None) == EVENT_ORDER[6]


