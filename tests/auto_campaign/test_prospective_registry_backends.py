from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from loto.auto_campaign.prospective_registry_backends import (
    POSTGRES_TABLES,
    record_mlflow,
    redact_uri,
)


@dataclass
class _Info:
    run_id: str


@dataclass
class _Data:
    tags: dict[str, str]


@dataclass
class _Run:
    info: _Info
    data: _Data


class _Experiment:
    experiment_id = "1"


class _FakeMlflowClient:
    def __init__(self) -> None:
        self.runs: dict[str, _Run] = {}
        self.params: dict[str, dict[str, str]] = {}
        self.metrics: dict[str, dict[str, float]] = {}
        self.artifacts: list[tuple[str, str, str | None]] = []
        self.terminated: list[tuple[str, str]] = []
        self.experiment_created = False

    def get_experiment_by_name(self, _name: str) -> _Experiment | None:
        return _Experiment() if self.experiment_created else None

    def create_experiment(self, _name: str) -> str:
        self.experiment_created = True
        return "1"

    def search_runs(
        self,
        _experiment_ids: list[str],
        *,
        filter_string: str,
        max_results: int,
    ) -> list[_Run]:
        assert max_results == 2
        matches: list[_Run] = []
        for run in self.runs.values():
            if all(
                f"tags.{key} = '{value}'" in filter_string
                for key, value in run.data.tags.items()
                if key in {
                    "registry_id",
                    "registry_role",
                    "candidate_key",
                    "seed_token",
                }
            ):
                matches.append(run)
        return matches

    def create_run(
        self,
        _experiment_id: str,
        *,
        tags: dict[str, str],
    ) -> _Run:
        run_id = f"run-{len(self.runs) + 1}"
        run = _Run(_Info(run_id), _Data(dict(tags)))
        self.runs[run_id] = run
        return run

    def log_batch(
        self,
        run_id: str,
        *,
        params: list[Any],
        metrics: list[Any],
    ) -> None:
        self.params[run_id] = {item.key: item.value for item in params}
        self.metrics[run_id] = {item.key: item.value for item in metrics}

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self.runs[run_id].data.tags[key] = value

    def get_run(self, run_id: str) -> _Run:
        return self.runs[run_id]

    def log_artifacts(
        self,
        run_id: str,
        local_dir: str,
        *,
        artifact_path: str | None = None,
    ) -> None:
        self.artifacts.append((run_id, local_dir, artifact_path))

    def set_terminated(self, run_id: str, *, status: str) -> None:
        self.terminated.append((run_id, status))


@dataclass
class _Metric:
    key: str
    value: float
    timestamp: int
    step: int


@dataclass
class _Param:
    key: str
    value: str


def _install_fake_mlflow(
    monkeypatch: Any,
    client: _FakeMlflowClient,
) -> None:
    module = types.ModuleType("mlflow")
    module.set_tracking_uri = lambda _uri: None
    module.MlflowClient = lambda: client
    entities = types.ModuleType("mlflow.entities")
    entities.Metric = _Metric
    entities.Param = _Param
    monkeypatch.setitem(sys.modules, "mlflow", module)
    monkeypatch.setitem(sys.modules, "mlflow.entities", entities)


def _payload() -> dict[str, Any]:
    return {
        "registry_id": "prospective-registry-test",
        "payload_sha256": "payload-sha",
        "scoring_id": "score-1",
        "registry_namespace": "production",
        "source": {
            "source_run_id": "prospective-1",
            "prediction_lock_sha256": "lock-sha",
            "scoring_report_sha256": "report-sha",
            "artifact_manifest_sha256": "manifest-sha",
        },
        "metric_policy": {"priority_metric": "hit_pm1"},
        "counts": {
            "candidate_count": 2,
            "seed_metric_rows": 2,
            "position_metric_rows": 10,
        },
        "scoring_report": {
            "champion": {
                "hit_pm1": 0.8,
                "all_positions_hit_pm1": 0.5,
                "mae": 0.7,
                "mse": 0.9,
                "rmse": 0.95,
            }
        },
    }


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "seed_metrics": pd.DataFrame(
            [
                {
                    "candidate_key": "model|AutoTFT|NONE|u_shared",
                    "seed_token": "1",
                    "seed": 1,
                    "source_type": "model",
                    "model_name": "AutoTFT",
                    "baseline_name": None,
                    "track": "u_shared",
                    "hit_pm1": 0.8,
                    "all_positions_hit_pm1": 0.5,
                    "mae": 0.7,
                    "mse": 0.9,
                    "rmse": 0.95,
                },
                {
                    "candidate_key": "baseline|NONE|last|baseline",
                    "seed_token": "NONE",
                    "seed": None,
                    "source_type": "baseline",
                    "model_name": None,
                    "baseline_name": "last",
                    "track": "baseline",
                    "hit_pm1": 0.4,
                    "all_positions_hit_pm1": 0.0,
                    "mae": 1.5,
                    "mse": 3.0,
                    "rmse": 1.73,
                },
            ]
        )
    }


def test_redact_uri_hides_credentials_and_query_values() -> None:
    value = redact_uri(
        "postgresql://user:password@db.example:5432/loto?sslmode=require&token=abc"
    )

    assert value == (
        "postgresql://user:***@db.example:5432/loto?"
        "sslmode=***&token=***"
    )
    assert "password" not in value
    assert "abc" not in value


def test_registry_postgres_tables_are_namespaced() -> None:
    assert len(POSTGRES_TABLES) == 5
    assert all(name.startswith("nf_prospective_registry_") for name in POSTGRES_TABLES)


def test_mlflow_parent_and_seed_children_are_idempotent(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    client = _FakeMlflowClient()
    _install_fake_mlflow(monkeypatch, client)
    evidence = tmp_path / "evidence"
    scoring = tmp_path / "scoring"
    evidence.mkdir()
    scoring.mkdir()
    (evidence / "REGISTRY_PAYLOAD.json").write_text("{}", encoding="utf-8")
    (scoring / "SCORING_REPORT.json").write_text("{}", encoding="utf-8")

    first = record_mlflow(
        "http://user:password@mlflow.local",
        "prospective-test",
        _payload(),
        _frames(),
        evidence_root=evidence,
        scoring_root=scoring,
        artifact_mode="metadata",
    )
    second = record_mlflow(
        "http://user:password@mlflow.local",
        "prospective-test",
        _payload(),
        _frames(),
        evidence_root=evidence,
        scoring_root=scoring,
        artifact_mode="metadata",
    )

    assert first["status"] == "PASS"
    assert first["parent_reused"] is False
    assert first["child_count"] == 2
    assert second["parent_run_id"] == first["parent_run_id"]
    assert second["parent_reused"] is True
    assert second["reused_child_count"] == 2
    assert len(client.runs) == 3
    parent = client.runs[first["parent_run_id"]]
    children = [
        run
        for run in client.runs.values()
        if run.data.tags.get("registry_role") == "seed"
    ]
    assert parent.data.tags["registry_role"] == "parent"
    assert all(
        child.data.tags["mlflow.parentRunId"] == first["parent_run_id"]
        for child in children
    )
    assert first["safe_uri"] == "http://user:***@mlflow.local"
    assert client.artifacts == [
        (first["parent_run_id"], str(evidence), "registry_evidence")
    ]
