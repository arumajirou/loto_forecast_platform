"""Unit tests for CLI startup and dry-run validation."""

from unittest.mock import MagicMock, patch

from loto_ops.cli import main


def test_cli_dry_run_success():
    """Test that main run --dry-run returns 0 when config loads successfully."""
    # Mock load_settings to return a dummy settings object
    mock_settings = MagicMock()
    mock_settings.pipeline = {"default_games": "all"}

    with (
        patch("loto_ops.config.load_settings", return_value=mock_settings),
        patch("sys.argv", ["loto-ops", "run", "--dry-run"]),
    ):
        exit_code = main()
        assert exit_code == 0


def test_cli_config_load_failure():
    """Test that main returns 1 when config loading raises an exception."""
    with (
        patch("loto_ops.config.load_settings", side_effect=FileNotFoundError("Config not found")),
        patch("sys.argv", ["loto-ops", "run"]),
    ):
        exit_code = main()
        assert exit_code == 1


def test_cli_pipeline_run_success():
    """Test that main run successfully invokes the orchestrator in non-dry-run mode."""
    mock_settings = MagicMock()
    mock_settings.pipeline = {"default_games": "all"}

    mock_orchestrator = MagicMock()
    mock_orchestrator.run_pipeline.return_value = {"all": {"status": "success"}}

    with (
        patch("loto_ops.config.load_settings", return_value=mock_settings),
        patch(
            "loto_ops.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orchestrator
        ),
        patch("sys.argv", ["loto-ops", "run"]),
    ):
        exit_code = main()
        assert exit_code == 0
        mock_orchestrator.run_pipeline.assert_called_once_with(["all"])
