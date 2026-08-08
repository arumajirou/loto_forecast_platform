from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from loto.orchestration.pipeline_downstream_preflight import (
    DownstreamCommitConflict,
    DownstreamCommitRetryable,
)
from loto.orchestration.pipeline_downstream_types import (
    DownstreamCommitReceipt,
    DownstreamCommitState,
    DownstreamCommitStatus,
    DownstreamStepState,
    DownstreamStepStatus,
    PreparedDownstreamCommit,
)

STEP_ORDER = (
    "release_bundle",
    "artifact_store",
    "mlflow",
    "legacy_registry",
    "platform_registry",
    "event_publication",
)


class DownstreamEffects(Protocol):
    def ensure_release(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]: ...

    def ensure_artifact_store(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]: ...

    def ensure_mlflow(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]: ...

    def ensure_legacy_registry(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]: ...

    def ensure_platform_registry(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]: ...

    def ensure_event(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _atomic_write_json(path: Path, payload: Any) -> None:
    if path.is_symlink():
        raise DownstreamCommitConflict(f"transaction artifact is a symlink: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_state(path: Path) -> DownstreamCommitState | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise DownstreamCommitConflict("downstream commit state is not a regular file")
    try:
        return DownstreamCommitState.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DownstreamCommitConflict("downstream commit state is invalid") from exc


def _load_receipt(path: Path) -> DownstreamCommitReceipt | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise DownstreamCommitConflict("downstream commit receipt is not a regular file")
    try:
        return DownstreamCommitReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DownstreamCommitConflict("downstream commit receipt is invalid") from exc


class _CommitLock:
    def __init__(self, path: Path, commit_id: str):
        self.path = path
        self.commit_id = commit_id
        self._acquired = False

    def __enter__(self) -> _CommitLock:
        payload = {
            "commit_id": self.commit_id,
            "pid": os.getpid(),
            "created_at": _utc_now().isoformat(),
        }
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise DownstreamCommitRetryable(
                f"downstream commit lock already exists: {self.path}"
            ) from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._acquired = True
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._acquired and self.path.exists():
            self.path.unlink()
        self._acquired = False


def _initial_state(
    prepared: PreparedDownstreamCommit,
) -> DownstreamCommitState:
    now = _utc_now()
    return DownstreamCommitState(
        commit_id=prepared.commit_id,
        run_id=prepared.run_id,
        ledger_sha256=prepared.ledger_sha256,
        snapshot_sha256=prepared.snapshot_sha256,
        status=DownstreamCommitStatus.PREPARED,
        attempt_count=0,
        created_at=now,
        updated_at=now,
        steps=[DownstreamStepState(name=name) for name in STEP_ORDER],
    )


def _verify_state_identity(
    state: DownstreamCommitState,
    prepared: PreparedDownstreamCommit,
) -> None:
    if (
        state.commit_id != prepared.commit_id
        or state.run_id != prepared.run_id
        or state.ledger_sha256 != prepared.ledger_sha256
        or state.snapshot_sha256 != prepared.snapshot_sha256
    ):
        raise DownstreamCommitConflict(
            "downstream commit state refers to another prepared snapshot"
        )


def _step_callable(
    effects: DownstreamEffects,
    step_name: str,
):
    return {
        "release_bundle": effects.ensure_release,
        "artifact_store": effects.ensure_artifact_store,
        "mlflow": effects.ensure_mlflow,
        "legacy_registry": effects.ensure_legacy_registry,
        "platform_registry": effects.ensure_platform_registry,
        "event_publication": effects.ensure_event,
    }[step_name]
