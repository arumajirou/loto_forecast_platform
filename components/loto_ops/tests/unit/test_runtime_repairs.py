from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from loto_ops.cli import main
from loto_ops.paths import ProjectPaths
from loto_ops.pipeline.orchestrator import PipelineOrchestrator


def _settings(tmp_path: Path):
    paths = ProjectPaths(
        ops_project=tmp_path,
        loto_life_project=tmp_path / "life",
        loto_forecast_project=tmp_path / "forecast",
        zip_output_dir=tmp_path / "zips-out",
    )
    return SimpleNamespace(
        paths=paths,
        db=SimpleNamespace(password="CHANGE_ME"),
        pipeline={"default_games": "all"},
        scheduler={},
        workflow={"selected_workflow": "A"},
        raw={},
    )


def test_preflight_exists_and_auto_fixes_local_dirs(tmp_path):
    settings = _settings(tmp_path)
    orchestrator = PipelineOrchestrator(settings)
    result = orchestrator.preflight(auto_fix=True)
    assert result["status"] == "PARTIAL"
    assert result["ready"] is True
    assert settings.paths.runs_dir.is_dir()
    assert settings.paths.artifacts_dir.is_dir()
    assert settings.paths.zip_output_dir.is_dir()
    assert result["ready_for_fast_pipeline"] is False


def test_compute_run_dir_uses_project_paths(tmp_path):
    settings = _settings(tmp_path)
    orchestrator = PipelineOrchestrator(settings)
    assert orchestrator._compute_run_dir("all", "loto_ops") == tmp_path / "runs" / "loto_ops_all"


def test_run_pipeline_records_outer_failure(tmp_path):
    settings = _settings(tmp_path)
    orchestrator = PipelineOrchestrator(settings)
    with patch.object(orchestrator, "_compute_run_dir", side_effect=RuntimeError("boom")):
        result = orchestrator.run_pipeline(["all"])
    assert result["all"]["status"] == "failed"
    assert result["all"]["error"] == "boom"


def test_cli_run_returns_failure_for_empty_results():
    mock_settings = MagicMock()
    mock_settings.pipeline = {"default_games": "all"}
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_pipeline.return_value = {}
    with (
        patch("loto_ops.config.load_settings", return_value=mock_settings),
        patch(
            "loto_ops.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orchestrator
        ),
        patch("sys.argv", ["loto-ops", "run"]),
    ):
        assert main() == 1


def test_cli_run_returns_failure_for_failed_game():
    mock_settings = MagicMock()
    mock_settings.pipeline = {"default_games": "all"}
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_pipeline.return_value = {"all": {"status": "failed", "error": "x"}}
    with (
        patch("loto_ops.config.load_settings", return_value=mock_settings),
        patch(
            "loto_ops.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orchestrator
        ),
        patch("sys.argv", ["loto-ops", "run"]),
    ):
        assert main() == 1


def test_load_settings_discovers_sibling_projects(tmp_path, monkeypatch):
    from loto_ops import config as config_module

    ops = tmp_path / "loto_ops_pipeline-fixed"
    life = tmp_path / "loto_life_feature_pipeline"
    forecast = tmp_path / "loto_neuralforecast_pipeline"
    (ops / "configs").mkdir(parents=True)
    life.mkdir()
    forecast.mkdir()
    config_path = ops / "configs" / "loto_ops.yaml"
    config_path.write_text(
        """
paths:
  ops_project: /missing/ops
  loto_life_project: /missing/life
  loto_forecast_project: /missing/forecast
  zip_output_dir: /missing/zips
pipeline:
  default_games: all
workflow:
  selected_workflow: A
db:
  password: CHANGE_ME
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("LOTO_OPS_PROJECT", raising=False)
    monkeypatch.delenv("LOTO_LIFE_PROJECT", raising=False)
    monkeypatch.delenv("LOTO_FORECAST_PROJECT", raising=False)
    monkeypatch.delenv("LOTO_ZIP_OUTPUT_DIR", raising=False)
    config_module._settings_cache.clear()

    settings = config_module.load_settings(config_path)
    assert settings.paths.ops_project == ops.resolve()
    assert settings.paths.loto_life_project == life.resolve()
    assert settings.paths.loto_forecast_project == forecast.resolve()
    assert settings.raw["runs_dir"] == str((ops / "runs").resolve())
