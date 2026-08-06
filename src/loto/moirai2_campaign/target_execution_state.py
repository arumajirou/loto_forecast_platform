from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from loto.moirai2_campaign.target_execution_common import (
    CUDA_LANE,
    EVENT_ORDER,
    LANE_DEVICES,
    SCHEMA_VERSION,
    STAGES,
    SUPPORTED_LANE,
    ArtifactRecord,
    TargetExecutionError,
    artifact_tree_sha256,
    sha256_payload,
)
from loto.moirai2_campaign.target_execution_validators import (
    validate_campaign_artifact,
    validate_candidate_artifact,
    validate_installation_artifact,
    validate_pair_artifact,
)


def verify_recorded_artifacts(state: Mapping[str, Any]) -> None:
    validate_state(state)
    artifacts = state.get("artifacts", {})
    for key, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            raise TargetExecutionError(f"artifact record is invalid: {key}")
        artifact_dir = Path(str(artifact.get("artifact_dir", "")))
        expected = str(artifact.get("artifact_tree_sha256", ""))
        actual = artifact_tree_sha256(artifact_dir)
        if actual != expected:
            raise TargetExecutionError(
                f"recorded artifact tree changed: key={key} "
                f"expected={expected} actual={actual}"
            )


def build_initial_state(
    *,
    run_id: str,
    snapshot_path: Path,
    source_identity: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    if not run_id or any(char in run_id for char in "/\\"):
        raise TargetExecutionError("run_id is invalid")
    if not snapshot_path.is_absolute():
        raise TargetExecutionError("snapshot_path must be absolute")
    if source_identity.get("worktree_clean") is not True:
        raise TargetExecutionError("source worktree must be clean")
    state = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "snapshot_path": str(snapshot_path),
        "source_identity": dict(source_identity),
        "created_at": created_at,
        "updated_at": created_at,
        "stage": STAGES[0],
        "events": [],
        "artifacts": {},
        "p9_oof_gate_open": False,
        "accuracy_claimed": False,
        "oof_executed": False,
        "holdout_executed": False,
        "prospective_executed": False,
    }
    state["state_payload_sha256"] = _state_payload_sha256(state)
    return state


def _state_payload_sha256(state: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in state.items() if key != "state_payload_sha256"}
    return sha256_payload(payload)


def validate_state(state: Mapping[str, Any]) -> None:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise TargetExecutionError("execution state schema differs")
    if state.get("state_payload_sha256") != _state_payload_sha256(state):
        raise TargetExecutionError("execution state payload SHA-256 differs")
    events = state.get("events")
    artifacts = state.get("artifacts")
    if not isinstance(events, list) or not isinstance(artifacts, dict):
        raise TargetExecutionError("execution state events or artifacts are invalid")
    if len(events) > len(EVENT_ORDER):
        raise TargetExecutionError("execution state contains too many events")
    previous_sha: str | None = None
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise TargetExecutionError("execution event must be an object")
        if event.get("sequence") != index + 1:
            raise TargetExecutionError("execution event sequence differs")
        if event.get("event_type") != EVENT_ORDER[index]:
            raise TargetExecutionError("execution event order differs")
        if event.get("previous_event_sha256") != previous_sha:
            raise TargetExecutionError("execution event hash chain differs")
        event_payload = {
            key: value for key, value in event.items() if key != "event_sha256"
        }
        expected_sha = sha256_payload(event_payload)
        if event.get("event_sha256") != expected_sha:
            raise TargetExecutionError("execution event SHA-256 differs")
        previous_sha = expected_sha
    if state.get("stage") != STAGES[len(events)]:
        raise TargetExecutionError("execution stage differs from event history")
    if state.get("p9_oof_gate_open") is not (len(events) == len(EVENT_ORDER)):
        raise TargetExecutionError("P9 gate differs from execution stage")
    if len(artifacts) != len(events):
        raise TargetExecutionError("artifact record count differs from event count")


def _artifact_key(event_type: str) -> str:
    return event_type.removesuffix("_recorded")


def append_event(
    state: Mapping[str, Any],
    *,
    event_type: str,
    runtime_lane: str | None,
    artifact_dir: Path,
    summary: Mapping[str, Any],
    recorded_at: str,
) -> dict[str, Any]:
    validate_state(state)
    events = list(state["events"])
    if len(events) >= len(EVENT_ORDER) or event_type != EVENT_ORDER[len(events)]:
        expected = EVENT_ORDER[len(events)] if len(events) < len(EVENT_ORDER) else None
        raise TargetExecutionError(
            f"invalid transition: expected={expected!r} actual={event_type!r}"
        )
    tree_sha = artifact_tree_sha256(artifact_dir)
    previous_sha = events[-1]["event_sha256"] if events else None
    event = {
        "sequence": len(events) + 1,
        "event_type": event_type,
        "runtime_lane": runtime_lane,
        "artifact_dir": str(artifact_dir.resolve()),
        "artifact_tree_sha256": tree_sha,
        "summary": dict(summary),
        "recorded_at": recorded_at,
        "previous_event_sha256": previous_sha,
    }
    event["event_sha256"] = sha256_payload(event)
    events.append(event)
    artifacts = dict(state["artifacts"])
    key = _artifact_key(event_type)
    if key in artifacts:
        raise TargetExecutionError(f"artifact key already exists: {key}")
    artifacts[key] = ArtifactRecord(
        key=key,
        event_type=event_type,
        runtime_lane=runtime_lane,
        artifact_dir=str(artifact_dir.resolve()),
        artifact_tree_sha256=tree_sha,
        summary=dict(summary),
    ).as_dict()
    updated = dict(state)
    updated.update(
        {
            "updated_at": recorded_at,
            "stage": STAGES[len(events)],
            "events": events,
            "artifacts": artifacts,
            "p9_oof_gate_open": len(events) == len(EVENT_ORDER),
        }
    )
    updated["state_payload_sha256"] = _state_payload_sha256(updated)
    validate_state(updated)
    return updated


def expected_next_event(state: Mapping[str, Any]) -> str | None:
    validate_state(state)
    index = len(state["events"])
    return EVENT_ORDER[index] if index < len(EVENT_ORDER) else None


def candidate_summary_for_lane(
    state: Mapping[str, Any],
    runtime_lane: str,
) -> Mapping[str, Any]:
    key = "supported_candidate" if runtime_lane == SUPPORTED_LANE else "cuda_candidate"
    artifact = state.get("artifacts", {}).get(key)
    if not isinstance(artifact, dict):
        raise TargetExecutionError(f"candidate artifact is not recorded for {runtime_lane}")
    summary = artifact.get("summary")
    if not isinstance(summary, dict):
        raise TargetExecutionError("candidate artifact summary is invalid")
    return summary


def campaign_dir_for_lane(state: Mapping[str, Any], runtime_lane: str) -> Path:
    key = "supported_campaign" if runtime_lane == SUPPORTED_LANE else "cuda_campaign"
    artifact = state.get("artifacts", {}).get(key)
    if not isinstance(artifact, dict):
        raise TargetExecutionError(f"campaign artifact is not recorded for {runtime_lane}")
    return Path(str(artifact["artifact_dir"]))


def event_type_for(kind: str, runtime_lane: str | None) -> str:
    if kind == "verification":
        if runtime_lane is not None:
            raise TargetExecutionError("pair verification does not accept a runtime lane")
        return "pair_verification_recorded"
    if runtime_lane not in LANE_DEVICES:
        raise TargetExecutionError("runtime lane is required")
    prefix = "supported" if runtime_lane == SUPPORTED_LANE else "cuda"
    mapping = {
        "candidate": f"{prefix}_candidate_recorded",
        "installation": f"{prefix}_installation_recorded",
        "campaign": f"{prefix}_campaign_recorded",
    }
    try:
        return mapping[kind]
    except KeyError as exc:
        raise TargetExecutionError(f"unsupported artifact kind: {kind}") from exc


def validator_for(
    kind: str,
) -> Callable[..., dict[str, Any]]:
    mapping: dict[str, Callable[..., dict[str, Any]]] = {
        "candidate": validate_candidate_artifact,
        "installation": validate_installation_artifact,
        "campaign": validate_campaign_artifact,
        "verification": validate_pair_artifact,
    }
    try:
        return mapping[kind]
    except KeyError as exc:
        raise TargetExecutionError(f"unsupported artifact kind: {kind}") from exc
