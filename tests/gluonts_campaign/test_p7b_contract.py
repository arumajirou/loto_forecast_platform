from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.p7b_contract import (
    P7BExecutionJournal,
    P7BExecutionManifest,
    P7BExecutionState,
    P7BSourceIdentity,
    P7BStage,
    P7BStageRecord,
    P7BStageState,
    sha256_json,
)


def source_identity() -> P7BSourceIdentity:
    return P7BSourceIdentity(
        repository_root="/repo",
        branch="feature",
        commit_sha="a" * 40,
        tracked_worktree_dirty=False,
        source_sha256={"environments/runner.py": "b" * 64},
    )


def pending_record(stage: P7BStage) -> P7BStageRecord:
    return P7BStageRecord(
        stage=stage,
        state=P7BStageState.PENDING,
        attempt=1,
    )


def test_journal_requires_exact_stage_set() -> None:
    stages = {stage: pending_record(stage) for stage in P7BStage}
    journal = P7BExecutionJournal(
        run_id="run",
        output_directory="/artifacts/run",
        started_at_utc="2026-08-05T00:00:00+00:00",
        updated_at_utc="2026-08-05T00:00:00+00:00",
        execution_state=P7BExecutionState.RUNNING,
        resume_count=0,
        source_identity=source_identity(),
        stages=stages,
    )
    assert set(journal.stages) == set(P7BStage)

    incomplete = dict(stages)
    incomplete.pop(P7BStage.AUDIT)
    with pytest.raises(ValidationError, match="every P7B stage"):
        P7BExecutionJournal(
            run_id="run",
            output_directory="/artifacts/run",
            started_at_utc="2026-08-05T00:00:00+00:00",
            updated_at_utc="2026-08-05T00:00:00+00:00",
            execution_state=P7BExecutionState.RUNNING,
            resume_count=0,
            source_identity=source_identity(),
            stages=incomplete,
        )


def test_completed_stage_requires_output_identity() -> None:
    with pytest.raises(ValidationError, match="output identity"):
        P7BStageRecord(
            stage=P7BStage.AUDIT,
            state=P7BStageState.COMPLETED,
            attempt=1,
            started_at_utc="2026-08-05T00:00:00+00:00",
            ended_at_utc="2026-08-05T00:01:00+00:00",
            return_code=1,
        )


def test_completed_stage_allows_nonzero_return_code() -> None:
    record = P7BStageRecord(
        stage=P7BStage.AUDIT,
        state=P7BStageState.COMPLETED,
        attempt=1,
        command=["python", "-m", "audit"],
        command_sha256="c" * 64,
        started_at_utc="2026-08-05T00:00:00+00:00",
        ended_at_utc="2026-08-05T00:01:00+00:00",
        return_code=2,
        output_identity_sha256="d" * 64,
    )
    assert record.return_code == 2


def test_manifest_requires_all_stage_identities() -> None:
    commands = {
        "compat_bootstrap": "a" * 64,
        "latest_bootstrap": "b" * 64,
        "audit": "c" * 64,
    }
    outputs = {
        "compat_bootstrap": "d" * 64,
        "latest_bootstrap": "e" * 64,
        "audit": "f" * 64,
    }
    manifest = P7BExecutionManifest(
        run_id="run",
        commit_sha="1" * 40,
        journal_sha256="2" * 64,
        stage_command_sha256=commands,
        stage_output_identity_sha256=outputs,
        audit_return_code=1,
        finalized_at_utc="2026-08-05T00:02:00+00:00",
    )
    assert manifest.audit_return_code == 1

    with pytest.raises(ValidationError, match="output identities"):
        P7BExecutionManifest(
            run_id="run",
            commit_sha="1" * 40,
            journal_sha256="2" * 64,
            stage_command_sha256=commands,
            stage_output_identity_sha256={"audit": "f" * 64},
            audit_return_code=1,
            finalized_at_utc="2026-08-05T00:02:00+00:00",
        )


def test_source_identity_rejects_path_escape() -> None:
    with pytest.raises(ValidationError, match="safe relative"):
        P7BSourceIdentity(
            repository_root="/repo",
            branch="feature",
            commit_sha="a" * 40,
            tracked_worktree_dirty=False,
            source_sha256={"../escape": "b" * 64},
        )


def test_canonical_hash_is_order_independent() -> None:
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})
