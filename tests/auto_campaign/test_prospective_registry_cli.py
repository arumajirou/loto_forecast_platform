from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.auto_campaign import cli


def test_register_scoring_routes_configless_options(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    project = tmp_path.resolve()
    captured: dict[str, Any] = {}

    def fake_register(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "PASS", "registry_id": "registry-1"}

    monkeypatch.setattr(cli, "register_prospective_scoring", fake_register)
    args = cli.build_parser().parse_args(
        [
            "--project-root",
            str(project),
            "register-scoring",
            "--run",
            "artifacts/scoring/run-1",
            "--output",
            "artifacts/registry/run-1",
            "--registry-namespace",
            "shadow",
            "--postgres-dsn-env",
            "TEST_POSTGRES_DSN",
            "--mlflow-uri",
            "http://mlflow.local",
            "--mlflow-experiment",
            "prospective-test",
            "--artifact-mode",
            "full",
        ]
    )

    result = cli._run_portable_command(args, project)

    assert result == {"status": "PASS", "registry_id": "registry-1"}
    assert captured["scoring_root"] == (project / "artifacts/scoring/run-1").resolve()
    assert captured["output"] == (project / "artifacts/registry/run-1").resolve()
    options = captured["options"]
    assert options.registry_namespace == "shadow"
    assert options.postgres_dsn_env == "TEST_POSTGRES_DSN"
    assert options.mlflow_uri == "http://mlflow.local"
    assert options.mlflow_experiment == "prospective-test"
    assert options.artifact_mode == "full"


def test_verify_registry_routes_without_campaign_config(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    project = tmp_path.resolve()
    expected = (project / "receipt").resolve()
    monkeypatch.setattr(
        cli,
        "verify_prospective_registry",
        lambda path: {"status": "PASS", "path": str(path)},
    )
    args = cli.build_parser().parse_args(
        [
            "--project-root",
            str(project),
            "verify-scoring-registry",
            "--run",
            "receipt",
        ]
    )

    result = cli._run_portable_command(args, project)

    assert result == {"status": "PASS", "path": str(expected)}


def test_registry_cli_returns_structured_failure(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    project = tmp_path.resolve()

    def fail(**_kwargs: Any) -> dict[str, Any]:
        raise ValueError("invalid registry source")

    monkeypatch.setattr(cli, "register_prospective_scoring", fail)
    args = cli.build_parser().parse_args(
        [
            "register-scoring",
            "--run",
            "scoring",
            "--output",
            "receipt",
            "--mlflow-uri",
            "http://mlflow.local",
        ]
    )

    result = cli._run_portable_command(args, project)

    assert result == {
        "status": "FAIL",
        "command": "register-scoring",
        "error_type": "ValueError",
        "error": "invalid registry source",
    }
