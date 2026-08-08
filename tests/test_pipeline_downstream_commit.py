from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.orchestration.pipeline_downstream_commit import (
    DownstreamCommitConflict,
    DownstreamCommitPreflightError,
    DownstreamCommitRetryable,
    execute_downstream_commit,
)
from loto.orchestration.pipeline_downstream_types import DownstreamCommitStatus


class FakeEffects:
    def __init__(self, *, fail_once: str | None = None):
        self.calls: list[str] = []
        self.fail_once = fail_once
        self.failed = False

    def _run(self, name: str) -> dict:
        self.calls.append(name)
        if self.fail_once == name and not self.failed:
            self.failed = True
            raise DownstreamCommitRetryable(f"{name}_temporary")
        return {"step": name, "ok": True}

    def ensure_release(self, prepared):
        return self._run("release_bundle")

    def ensure_artifact_store(self, prepared):
        return self._run("artifact_store")

    def ensure_mlflow(self, prepared):
        return self._run("mlflow")

    def ensure_legacy_registry(self, prepared):
        return self._run("legacy_registry")

    def ensure_platform_registry(self, prepared):
        return self._run("platform_registry")

    def ensure_event(self, prepared):
        return self._run("event_publication")


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def make_staged_output(root: Path) -> dict:
    root.mkdir()
    run_id = "pipeline-ledger-test"
    ledger_sha = "a" * 64
    forecast = {
        "forecast_id": "forecast-test",
        "draw_id": "loto7-11",
        "model_id": "uniform",
        "data_version": "test-v1",
        "feature_set_id": "features-v1",
        "metadata": {"run_id": run_id},
        "candidates": [],
        "combination": {"numbers": [1, 2, 3, 4, 5, 6, 7]},
    }
    _write_json(
        root / "downstream_commit_plan.json",
        {
            "status": "READY_FOR_DOWNSTREAM_COMMIT",
            "run_id": run_id,
            "ledger_sha256": ledger_sha,
            "executed": False,
            "deferred_operations": [
                "Registry.record_stage",
                "Registry.record_forecast",
                ("PlatformRegistry.create_run/update_run/register_forecast/register_model"),
                "MlflowBridge.record_run",
                "create_release_bundle",
                "ArtifactStore.put_file",
                "EventPublisher.publish",
            ],
            "reason": "test",
        },
    )
    _write_json(
        root / "pipeline_data_access_ledger.json",
        {
            "run_id": run_id,
            "ledger_sha256": ledger_sha,
        },
    )
    _write_json(
        root / "pipeline_data_access_validation.json",
        {
            "status": "PASS",
            "run_id": run_id,
            "ledger_sha256": ledger_sha,
            "error_count": 0,
            "warning_count": 0,
            "verified_event_count": 8,
            "findings": [],
        },
    )
    _write_json(
        root / "pipeline_data_access_report.json",
        {
            "status": "PASS",
            "run_id": run_id,
            "complete": True,
            "ledger_sha256": ledger_sha,
            "coverage_gaps": [],
            "downstream_commit_executed": False,
        },
    )
    _write_json(root / "forecast.json", forecast)
    _write_json(
        root / "forecast.sealed.json",
        {
            "payload": forecast,
            "signature": "test",
            "payload_sha256": "b" * 64,
        },
    )
    _write_json(
        root / "evaluation.json",
        {
            "champion": "uniform",
            "uniform": {
                "within_1_rate": 0.2,
                "position_mae": 3.0,
                "position_mse": 12.0,
            },
            "frequency": {
                "within_1_rate": 0.1,
                "position_mae": 4.0,
                "position_mse": 16.0,
            },
        },
    )
    for name in (
        "dataset_manifest.json",
        "feature_manifest.json",
        "resource_evidence.json",
    ):
        _write_json(root / name, {"name": name})
    for name in ("canonical.csv", "candidate_features.csv"):
        (root / name).write_text("a,b\n1,2\n", encoding="utf-8")
    return {
        "run_id": run_id,
        "ledger_sha256": ledger_sha,
        "forecast": forecast,
    }


def fake_validator(ledger, saved):
    return {
        "run_id": ledger["run_id"],
        "ledger_sha256": ledger["ledger_sha256"],
        "verified_events": saved["verified_event_count"],
    }


def fake_seal_verifier(sealed, secret):
    return sealed.get("signature") == "test" and len(secret) >= 16


def execute(root: Path, effects: FakeEffects):
    return execute_downstream_commit(
        root,
        secret=b"x" * 32,
        effects=effects,
        ledger_validator=fake_validator,
        seal_verifier=fake_seal_verifier,
    )


def test_success_and_receipt_short_circuit(tmp_path: Path) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    effects = FakeEffects()

    receipt = execute(root, effects)
    assert receipt.status is DownstreamCommitStatus.COMMITTED
    assert effects.calls == [
        "release_bundle",
        "artifact_store",
        "mlflow",
        "legacy_registry",
        "platform_registry",
        "event_publication",
    ]
    assert (root / "downstream_commit_state.json").is_file()
    assert (root / "downstream_commit_receipt.json").is_file()

    second = FakeEffects()
    repeated = execute(root, second)
    assert repeated.commit_id == receipt.commit_id
    assert second.calls == []


def test_retry_skips_completed_steps(tmp_path: Path) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    effects = FakeEffects(fail_once="mlflow")

    with pytest.raises(
        DownstreamCommitRetryable,
        match="mlflow_temporary",
    ):
        execute(root, effects)

    state = json.loads((root / "downstream_commit_state.json").read_text())
    assert state["status"] == "RETRY_REQUIRED"
    assert state["steps"][0]["status"] == "SUCCEEDED"
    assert state["steps"][1]["status"] == "SUCCEEDED"
    assert state["steps"][2]["status"] == "FAILED"

    receipt = execute(root, effects)
    assert receipt.status is DownstreamCommitStatus.COMMITTED
    assert effects.calls.count("release_bundle") == 1
    assert effects.calls.count("artifact_store") == 1
    assert effects.calls.count("mlflow") == 2
    assert effects.calls.count("event_publication") == 1


def test_changed_snapshot_conflicts_with_journal(tmp_path: Path) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    effects = FakeEffects(fail_once="mlflow")
    with pytest.raises(DownstreamCommitRetryable):
        execute(root, effects)

    with (root / "canonical.csv").open("a", encoding="utf-8") as handle:
        handle.write("3,4\n")
    with pytest.raises(
        DownstreamCommitConflict,
        match="another prepared snapshot",
    ):
        execute(root, FakeEffects())


def test_invalid_plan_blocks_before_state(tmp_path: Path) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    plan_path = root / "downstream_commit_plan.json"
    plan = json.loads(plan_path.read_text())
    plan["deferred_operations"].remove("MlflowBridge.record_run")
    _write_json(plan_path, plan)

    effects = FakeEffects()
    with pytest.raises(
        DownstreamCommitPreflightError,
        match="missing operations",
    ):
        execute(root, effects)
    assert effects.calls == []
    assert not (root / "downstream_commit_state.json").exists()


def test_unverified_seal_blocks_before_side_effects(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    sealed_path = root / "forecast.sealed.json"
    sealed = json.loads(sealed_path.read_text())
    sealed["signature"] = "bad"
    _write_json(sealed_path, sealed)

    effects = FakeEffects()
    with pytest.raises(
        DownstreamCommitPreflightError,
        match="seal verification failed",
    ):
        execute(root, effects)
    assert effects.calls == []


def test_existing_lock_is_retryable(tmp_path: Path) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    (root / "downstream_commit.lock").write_text(
        "{}\n",
        encoding="utf-8",
    )
    with pytest.raises(
        DownstreamCommitRetryable,
        match="lock already exists",
    ):
        execute(root, FakeEffects())


def test_conflicting_receipt_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    _write_json(
        root / "downstream_commit_receipt.json",
        {
            "schema_version": "1.0.0",
            "status": "COMMITTED",
            "commit_id": "0" * 64,
            "run_id": "other",
            "ledger_sha256": "a" * 64,
            "snapshot_sha256": "b" * 64,
            "release_id": "release-other",
            "forecast_id": "forecast-other",
            "model_id": "uniform",
            "committed_at": "2026-01-01T00:00:00Z",
            "step_results": {},
            "non_claims": [],
        },
    )
    with pytest.raises(
        DownstreamCommitConflict,
        match="receipt conflicts",
    ):
        execute(root, FakeEffects())


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "run"
    make_staged_output(root)
    (root / "evaluation.json").write_text(
        '{"champion":"uniform","champion":"frequency"}',
        encoding="utf-8",
    )
    with pytest.raises(
        DownstreamCommitPreflightError,
        match="duplicate JSON key",
    ):
        execute(root, FakeEffects())
