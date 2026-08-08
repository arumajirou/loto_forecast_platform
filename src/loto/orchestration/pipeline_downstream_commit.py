from __future__ import annotations

from pathlib import Path

from loto.orchestration.pipeline_downstream_journal import (
    STEP_ORDER,
    DownstreamEffects,
    _CommitLock,
    _atomic_write_json,
    _initial_state,
    _load_receipt,
    _load_state,
    _step_callable,
    _utc_now,
    _verify_state_identity,
)
from loto.orchestration.pipeline_downstream_preflight import (
    DownstreamCommitConflict,
    DownstreamCommitError,
    DownstreamCommitPreflightError,
    DownstreamCommitRetryable,
    prepare_downstream_commit,
    verify_prepared_snapshot,
)
from loto.orchestration.pipeline_downstream_types import (
    DownstreamCommitReceipt,
    DownstreamCommitStatus,
    DownstreamStepStatus,
)


def execute_downstream_commit(
    output_dir: str | Path,
    *,
    secret: bytes,
    effects: DownstreamEffects,
    ledger_validator=None,
    seal_verifier=None,
) -> DownstreamCommitReceipt:
    prepared = prepare_downstream_commit(
        output_dir,
        secret=secret,
        ledger_validator=ledger_validator,
        seal_verifier=seal_verifier,
    )
    root = prepared.root
    state_path = root / "downstream_commit_state.json"
    receipt_path = root / "downstream_commit_receipt.json"
    lock_path = root / "downstream_commit.lock"

    existing_receipt = _load_receipt(receipt_path)
    if existing_receipt is not None:
        if (
            existing_receipt.commit_id != prepared.commit_id
            or existing_receipt.status is not DownstreamCommitStatus.COMMITTED
            or set(existing_receipt.step_results) != set(STEP_ORDER)
        ):
            raise DownstreamCommitConflict("existing receipt conflicts with prepared commit")
        existing_state = _load_state(state_path)
        if existing_state is None:
            raise DownstreamCommitConflict("committed receipt exists without transaction state")
        _verify_state_identity(existing_state, prepared)
        if existing_state.status is not DownstreamCommitStatus.COMMITTED or any(
            item.status is not DownstreamStepStatus.SUCCEEDED for item in existing_state.steps
        ):
            raise DownstreamCommitConflict("receipt and transaction state disagree")
        verify_prepared_snapshot(prepared)
        return existing_receipt

    with _CommitLock(lock_path, prepared.commit_id):
        verify_prepared_snapshot(prepared)
        state = _load_state(state_path) or _initial_state(prepared)
        _verify_state_identity(state, prepared)
        state.attempt_count += 1
        state.status = DownstreamCommitStatus.IN_PROGRESS
        state.updated_at = _utc_now()
        _atomic_write_json(state_path, state.model_dump(mode="json"))

        for step in state.steps:
            if step.status is DownstreamStepStatus.SUCCEEDED:
                continue
            step.status = DownstreamStepStatus.RUNNING
            step.attempts += 1
            step.started_at = _utc_now()
            step.finished_at = None
            step.error = None
            state.updated_at = _utc_now()
            _atomic_write_json(
                state_path,
                state.model_dump(mode="json"),
            )
            verify_prepared_snapshot(prepared)
            try:
                result = _step_callable(
                    effects,
                    step.name,
                )(prepared)
                verify_prepared_snapshot(prepared)
            except DownstreamCommitConflict as exc:
                step.status = DownstreamStepStatus.FAILED
                step.finished_at = _utc_now()
                step.error = f"{type(exc).__name__}:{str(exc)[:3500]}"
                state.status = DownstreamCommitStatus.RETRY_REQUIRED
                state.updated_at = _utc_now()
                _atomic_write_json(
                    state_path,
                    state.model_dump(mode="json"),
                )
                raise
            except Exception as exc:
                step.status = DownstreamStepStatus.FAILED
                step.finished_at = _utc_now()
                step.error = f"{type(exc).__name__}:{str(exc)[:3500]}"
                state.status = DownstreamCommitStatus.RETRY_REQUIRED
                state.updated_at = _utc_now()
                _atomic_write_json(
                    state_path,
                    state.model_dump(mode="json"),
                )
                if isinstance(exc, DownstreamCommitRetryable):
                    raise
                raise DownstreamCommitRetryable(
                    f"{step.name} failed: {type(exc).__name__}:{str(exc)[:500]}"
                ) from exc
            step.status = DownstreamStepStatus.SUCCEEDED
            step.finished_at = _utc_now()
            step.result = result
            state.updated_at = _utc_now()
            _atomic_write_json(
                state_path,
                state.model_dump(mode="json"),
            )

        verify_prepared_snapshot(prepared)
        receipt = DownstreamCommitReceipt(
            status=DownstreamCommitStatus.COMMITTED,
            commit_id=prepared.commit_id,
            run_id=prepared.run_id,
            ledger_sha256=prepared.ledger_sha256,
            snapshot_sha256=prepared.snapshot_sha256,
            release_id=prepared.release_id,
            forecast_id=prepared.forecast_id,
            model_id=prepared.model_id,
            committed_at=_utc_now(),
            step_results={item.name: dict(item.result) for item in state.steps},
        )
        _atomic_write_json(
            receipt_path,
            receipt.model_dump(mode="json"),
        )
        state.status = DownstreamCommitStatus.COMMITTED
        state.updated_at = _utc_now()
        _atomic_write_json(
            state_path,
            state.model_dump(mode="json"),
        )
        return receipt


__all__ = [
    "DownstreamCommitConflict",
    "DownstreamCommitError",
    "DownstreamCommitPreflightError",
    "DownstreamCommitRetryable",
    "execute_downstream_commit",
]
