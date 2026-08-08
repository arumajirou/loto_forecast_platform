from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.target_execution import (  # noqa: E402
    CUDA_LANE,
    MANIFEST_FILENAME,
    SHA_FILENAME,
    STATE_FILENAME,
    SUPPORTED_LANE,
    TargetExecutionError,
    append_event,
    campaign_dir_for_lane,
    candidate_summary_for_lane,
    event_type_for,
    load_json_object,
    sha256_file,
    validate_campaign_artifact,
    validate_candidate_artifact,
    validate_installation_artifact,
    validate_pair_artifact,
    validate_state,
    verify_control_integrity,
    verify_recorded_artifacts,
    write_json_atomic,
)


def _write_control_manifest(control_dir: Path) -> None:
    manifest_path = control_dir / MANIFEST_FILENAME
    sha_path = control_dir / SHA_FILENAME
    manifest_path.unlink(missing_ok=True)
    sha_path.unlink(missing_ok=True)
    files = sorted(
        path.relative_to(control_dir).as_posix()
        for path in control_dir.rglob("*")
        if path.is_file()
    )
    write_json_atomic(
        manifest_path,
        {
            "schema_version": "moirai2-p8d-control-artifacts-v1",
            "files": files,
            "file_count": len(files),
        },
    )
    paths = sorted(path for path in control_dir.rglob("*") if path.is_file() and path != sha_path)
    sha_path.write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(control_dir).as_posix()}\n" for path in paths
        ),
        encoding="utf-8",
    )


def _acquire_lock(control_dir: Path) -> Path:
    lock_path = control_dir / ".p8d-record.lock"
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise TargetExecutionError("another record operation is active") from exc
    os.close(descriptor)
    return lock_path


def _record(
    *,
    control_dir: Path,
    kind: str,
    runtime_lane: str | None,
    artifact_dir: Path,
) -> dict[str, object]:
    verify_control_integrity(control_dir)
    state_path = control_dir / STATE_FILENAME
    state = load_json_object(state_path)
    validate_state(state)
    verify_recorded_artifacts(state)
    source_commit = str(state["source_identity"]["commit_sha"])
    if kind == "candidate":
        assert runtime_lane is not None
        summary = validate_candidate_artifact(
            artifact_dir,
            runtime_lane=runtime_lane,
        )
    elif kind == "installation":
        assert runtime_lane is not None
        summary = validate_installation_artifact(
            artifact_dir,
            runtime_lane=runtime_lane,
            candidate_summary=candidate_summary_for_lane(state, runtime_lane),
        )
    elif kind == "campaign":
        assert runtime_lane is not None
        summary = validate_campaign_artifact(
            artifact_dir,
            runtime_lane=runtime_lane,
            source_commit=source_commit,
        )
    elif kind == "verification":
        summary = validate_pair_artifact(
            artifact_dir,
            supported_campaign_dir=campaign_dir_for_lane(state, SUPPORTED_LANE),
            cuda_campaign_dir=campaign_dir_for_lane(state, CUDA_LANE),
            source_commit=source_commit,
        )
    else:
        raise TargetExecutionError(f"unsupported record kind: {kind}")
    event_type = event_type_for(kind, runtime_lane)
    recorded_at = datetime.now(timezone.utc).isoformat()
    updated = append_event(
        state,
        event_type=event_type,
        runtime_lane=runtime_lane,
        artifact_dir=artifact_dir,
        summary=summary,
        recorded_at=recorded_at,
    )
    checkpoint = control_dir / "checkpoints" / (f"{len(updated['events']):04d}-{event_type}.json")
    write_json_atomic(checkpoint, updated["events"][-1])
    write_json_atomic(state_path, updated)
    _write_control_manifest(control_dir)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and record one Moirai P8D target-host artifact"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, kind in (
        ("record-candidate", "candidate"),
        ("record-installation", "installation"),
        ("record-campaign", "campaign"),
    ):
        sub = subparsers.add_parser(command)
        sub.set_defaults(kind=kind)
        sub.add_argument("--control-dir", required=True, type=Path)
        sub.add_argument(
            "--runtime-lane",
            required=True,
            choices=(SUPPORTED_LANE, CUDA_LANE),
        )
        sub.add_argument("--artifact-dir", required=True, type=Path)
    final = subparsers.add_parser("record-verification")
    final.set_defaults(kind="verification", runtime_lane=None)
    final.add_argument("--control-dir", required=True, type=Path)
    final.add_argument("--artifact-dir", required=True, type=Path)
    arguments = parser.parse_args()
    control_dir = arguments.control_dir.resolve()
    if not control_dir.is_dir():
        raise SystemExit(f"control directory is missing: {control_dir}")
    artifact_dir = arguments.artifact_dir.resolve()
    lock_path = _acquire_lock(control_dir)
    try:
        updated = _record(
            control_dir=control_dir,
            kind=arguments.kind,
            runtime_lane=getattr(arguments, "runtime_lane", None),
            artifact_dir=artifact_dir,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    finally:
        lock_path.unlink(missing_ok=True)
    print(json.dumps(updated, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
