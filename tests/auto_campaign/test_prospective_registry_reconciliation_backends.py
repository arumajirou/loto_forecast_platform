from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from loto.auto_campaign.prospective_registry_reconciliation_backends import (
    query_mlflow,
    query_postgres,
)


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def fetchall(self) -> list[Any]:
        return [SimpleNamespace(_mapping=row) for row in self.rows]


class _Connection:
    def execute(self, statement: str, parameters: dict[str, Any]) -> _Rows:
        text = str(statement)
        registry_id = parameters["registry_id"]
        if "registry_runs" in text:
            return _Rows([{"registry_id": registry_id, "status": "PASS"}])
        if "candidates" in text:
            return _Rows([{"registry_id": registry_id, "candidate_key": "c1"}])
        if "seed_metrics" in text:
            return _Rows([{"registry_id": registry_id, "candidate_key": "c1"}])
        if "position_metrics" in text:
            return _Rows([{"registry_id": registry_id, "row_key": "r1"}])
        return _Rows([{"registry_id": registry_id, "path": "a"}])

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _Engine:
    def __init__(self) -> None:
        self.url = SimpleNamespace(
            render_as_string=lambda hide_password: (
                "postgresql://user:***@db/loto"
                if hide_password
                else "postgresql://user:secret@db/loto"
            )
        )

    def connect(self) -> _Connection:
        return _Connection()

    def dispose(self) -> None:
        return None


def test_postgres_probe_is_read_only_and_redacts_uri(monkeypatch) -> None:
    sqlalchemy = SimpleNamespace(
        create_engine=lambda _dsn, future: _Engine(),
        text=lambda value: value,
    )
    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy)

    result = query_postgres(
        "postgresql://user:secret@db/loto",
        {"registry_id": "registry-1"},
    )

    assert result["status"] == "PASS"
    assert result["safe_uri"] == "postgresql://user:***@db/loto"
    assert result["run_rows"] == [
        {"registry_id": "registry-1", "status": "PASS"}
    ]
    assert result["candidates"][0]["candidate_key"] == "c1"


class _Run:
    def __init__(
        self,
        run_id: str,
        role: str,
        *,
        candidate_key: str | None = None,
        seed_token: str | None = None,
    ) -> None:
        tags = {
            "registry_id": "registry-1",
            "registry_role": role,
            "payload_sha256": "a" * 64,
        }
        if candidate_key is not None:
            tags["candidate_key"] = candidate_key
        if seed_token is not None:
            tags["seed_token"] = seed_token
        self.info = SimpleNamespace(
            run_id=run_id,
            status="FINISHED",
            experiment_id="10",
        )
        self.data = SimpleNamespace(
            tags=tags,
            params={},
            metrics={"hit_pm1": 0.8},
        )


class _MlflowClient:
    def __init__(self, artifact: Path) -> None:
        self.artifact = artifact

    def get_experiment_by_name(self, _name: str) -> Any:
        return SimpleNamespace(experiment_id="10")

    def search_runs(
        self,
        _experiment_ids: list[str],
        *,
        filter_string: str,
        max_results: int,
    ) -> list[_Run]:
        assert max_results >= 2
        if "registry_role = 'parent'" in filter_string:
            return [_Run("parent-1", "parent")]
        return [_Run("child-1", "seed", candidate_key="c1", seed_token="1")]

    def download_artifacts(
        self,
        _run_id: str,
        _artifact_path: str,
        _target: str,
    ) -> str:
        return str(self.artifact)


def test_mlflow_probe_reads_parent_children_and_artifact_hash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact = tmp_path / "REGISTRY_PAYLOAD.json"
    artifact.write_text('{"registry_id":"registry-1"}\n', encoding="utf-8")
    client = _MlflowClient(artifact)
    mlflow = SimpleNamespace(
        set_tracking_uri=lambda _uri: None,
        MlflowClient=lambda: client,
    )
    monkeypatch.setitem(sys.modules, "mlflow", mlflow)

    result = query_mlflow(
        "http://user:secret@mlflow:5000",
        "experiment",
        {
            "registry_id": "registry-1",
            "mlflow_artifacts": [
                {
                    "path": "registry_evidence/REGISTRY_PAYLOAD.json",
                    "sha256": "unused-by-probe",
                }
            ],
        },
        require_remote_artifacts=True,
    )

    assert result["status"] == "PASS"
    assert result["safe_uri"] == "http://user:***@mlflow:5000"
    assert result["parent_runs"][0]["run_id"] == "parent-1"
    assert result["child_runs"][0]["run_id"] == "child-1"
    assert len(result["artifacts"][0]["sha256"]) == 64
