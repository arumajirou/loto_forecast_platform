from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from loto.orchestration.pipeline_downstream_commit import (
    DownstreamCommitConflict,
    DownstreamCommitRetryable,
    execute_downstream_commit,
)
from loto.orchestration.pipeline_downstream_effects import (
    DefaultDownstreamEffects,
    DownstreamCommitConfig,
)


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


def _install_fake_mlflow(monkeypatch):
    import types

    module = types.ModuleType("mlflow")
    experiments = {}
    runs = []
    current = {"run": None}

    def set_tracking_uri(uri):
        module.tracking_uri = uri

    def get_experiment_by_name(name):
        value = experiments.get(name)
        return None if value is None else types.SimpleNamespace(experiment_id=value)

    def create_experiment(name):
        value = str(len(experiments) + 1)
        experiments[name] = value
        return value

    def search_runs(
        experiment_ids,
        filter_string,
        max_results,
        output_format,
    ):
        commit_id = filter_string.split("'")[1]
        return [run for run in runs if run.data.tags.get("loto_commit_id") == commit_id][
            :max_results
        ]

    class Context:
        def __init__(self, run):
            self.run = run

        def __enter__(self):
            current["run"] = self.run
            runs.append(self.run)
            return self.run

        def __exit__(self, exc_type, exc, traceback):
            current["run"] = None

    def start_run(experiment_id, run_name):
        run = types.SimpleNamespace(
            info=types.SimpleNamespace(run_id=f"mlflow-{len(runs) + 1}"),
            data=types.SimpleNamespace(tags={}),
        )
        return Context(run)

    def set_tag(name, value):
        current["run"].data.tags[name] = value

    module.set_tracking_uri = set_tracking_uri
    module.get_experiment_by_name = get_experiment_by_name
    module.create_experiment = create_experiment
    module.search_runs = search_runs
    module.start_run = start_run
    module.set_tag = set_tag
    module.log_params = lambda value: None
    module.log_metrics = lambda value: None
    module.log_artifact = lambda value: None
    monkeypatch.setitem(__import__("sys").modules, "mlflow", module)
    return runs


def test_default_effects_are_idempotent_with_local_backends(
    tmp_path: Path,
    monkeypatch,
) -> None:

    from loto.orchestration.pipeline_downstream_effects import (
        DefaultDownstreamEffects,
        DownstreamCommitConfig,
    )

    root = tmp_path / "run"
    make_staged_output(root)
    mlflow_runs = _install_fake_mlflow(monkeypatch)
    config = DownstreamCommitConfig(
        registry_path=root / "registry.sqlite3",
        platform_registry_url=str(root / "platform.sqlite3"),
        artifact_store_root=root / "artifact_store",
        events_path=root / "events.jsonl",
        mlflow_tracking_uri="file:///test",
        mlflow_experiment_name="test",
    )
    effects = DefaultDownstreamEffects(config)
    first = execute(root, effects)
    second = execute(root, DefaultDownstreamEffects(config))
    assert first.commit_id == second.commit_id
    assert len(mlflow_runs) == 1

    with sqlite3.connect(root / "registry.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM stage_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0] == 1
    with sqlite3.connect(root / "platform.sqlite3") as connection:
        for table in (
            "runs",
            "tasks",
            "models",
            "forecasts",
            "audit_log",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
    assert len((root / "events.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_platform_model_conflict_blocks_candidate_registration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from loto.registry.full import PlatformRegistry

    root = tmp_path / "run"
    make_staged_output(root)
    _install_fake_mlflow(monkeypatch)
    platform_path = root / "platform.sqlite3"
    platform = PlatformRegistry(platform_path)
    platform.register_model(
        "uniform",
        "other",
        "file:///other",
        {"position_mae": 99.0},
        {"commit_id": "other"},
    )
    config = DownstreamCommitConfig(
        registry_path=root / "registry.sqlite3",
        platform_registry_url=str(platform_path),
        artifact_store_root=root / "artifact_store",
        events_path=root / "events.jsonl",
        mlflow_tracking_uri="file:///test",
        mlflow_experiment_name="test",
    )
    with pytest.raises(
        DownstreamCommitConflict,
        match="model_id already refers",
    ):
        execute(
            root,
            DefaultDownstreamEffects(config),
        )
    state = json.loads((root / "downstream_commit_state.json").read_text())
    assert state["status"] == "RETRY_REQUIRED"
    assert not (root / "downstream_commit_receipt.json").exists()
