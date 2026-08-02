"""Test session handover functionality.

Verifies export-handover and import-handover CLI subcommands work correctly
for JSON data round-trip between run_manifest and handover files.
"""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import loto_ops.cli as cli_module
from loto_ops.cli import _cmd_export_handover, _cmd_import_handover

# Use actual filesystem paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_RUNTIME = Path(os.getenv("LOTO_TEST_RUNTIME", PROJECT_ROOT / ".test-runtime"))
RUNS_DIR = TEST_RUNTIME / "runs"
HANDOVER_PATH = TEST_RUNTIME / "handovers" / "latest_handover.json"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
HANDOVER_PATH.parent.mkdir(parents=True, exist_ok=True)
cli_module.RUNS_DIR = RUNS_DIR
cli_module.HANDOVER_DIR = HANDOVER_PATH.parent
cli_module.HANDOVER_PATH = HANDOVER_PATH


def _make_manifest(
    status="success",
    run_id="run_test_20260719_120000",
    last_successful_stage=None,
    error_message=None,
    **overrides,
):
    """Helper to build a valid manifest dict for testing."""
    manifest = {
        "run_id": run_id,
        "status": status,
        "last_successful_stage": last_successful_stage,
        "next_stage": None,
        "artifacts": [
            {"name": "model.parquet", "type": "parquet"},
            {"name": "report.pdf", "type": "pdf"},
        ],
        "error_message": error_message,
    }
    manifest.update(overrides)
    return manifest


def test_export_handover_success():
    """Test export-handover with a successful run creates correct handover JSON."""
    # Create the actual run directory and manifest
    actual_run_dir = RUNS_DIR / "run_test_20260719_120000"
    actual_run_dir.mkdir(exist_ok=True)

    # Note: manifest must include last_successful_stage explicitly
    manifest_data = _make_manifest(status="success", last_successful_stage="model_evaluation")
    manifest_path = actual_run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest_data))

    # Execute export-handover
    args = MagicMock()
    args.run_id = "run_test_20260719_120000"
    result = _cmd_export_handover(args)

    assert result == 0
    assert HANDOVER_PATH.exists()

    with open(HANDOVER_PATH) as f:
        handover_data = json.load(f)

    assert handover_data["run_id"] == "run_test_20260719_120000"
    assert handover_data["status"] == "success"
    assert handover_data["last_successful_stage"] == "model_evaluation"
    assert handover_data["next_stage"] is None
    assert len(handover_data["artifacts"]) == 2
    assert handover_data["error_message"] is None

    # Cleanup
    if HANDOVER_PATH.exists():
        HANDOVER_PATH.unlink()
    if actual_run_dir.exists():
        shutil.rmtree(actual_run_dir)


def test_export_handover_failed():
    """Test export-handover with a failed run includes error info."""
    actual_run_dir = RUNS_DIR / "run_test_20260719_120000_failed"
    actual_run_dir.mkdir(exist_ok=True)

    manifest_data = _make_manifest(
        status="failed",
        run_id="run_test_20260719_120000_failed",
        last_successful_stage=None,
        error_message="(psycopg.OperationalError) connection failed",
    )
    (actual_run_dir / "run_manifest.json").write_text(json.dumps(manifest_data))

    # Execute export-handover
    args = MagicMock()
    args.run_id = "run_test_20260719_120000_failed"
    result = _cmd_export_handover(args)

    assert result == 0
    assert HANDOVER_PATH.exists()

    with open(HANDOVER_PATH) as f:
        handover_data = json.load(f)

    assert handover_data["run_id"] == "run_test_20260719_120000_failed"
    assert handover_data["status"] == "failed"
    assert handover_data["last_successful_stage"] is None
    assert handover_data["error_message"] == "(psycopg.OperationalError) connection failed"

    # Cleanup
    if HANDOVER_PATH.exists():
        HANDOVER_PATH.unlink()
    if actual_run_dir.exists():
        shutil.rmtree(actual_run_dir)


def test_export_handover_fallback_to_latest():
    """Test that export-handover falls back to the latest run when --run-id is None."""
    # Create two run directories
    for run_name in ["run_fallback_001", "run_fallback_002"]:
        run_dir = RUNS_DIR / run_name
        run_dir.mkdir(exist_ok=True)
        if run_name == "run_fallback_001":
            data = _make_manifest(run_id=run_name, status="success")
        else:
            data = _make_manifest(run_id=run_name, status="warning", error_message="Minor issue")
        (run_dir / "run_manifest.json").write_text(json.dumps(data))

    # Execute export-handover without specifying run_id
    args = MagicMock()
    args.run_id = None
    result = _cmd_export_handover(args)

    assert result == 0
    assert HANDOVER_PATH.exists()

    with open(HANDOVER_PATH) as f:
        handover_data = json.load(f)

    # The latest (lexicographically) should be run_fallback_002
    assert handover_data["run_id"] == "run_fallback_002"
    assert handover_data["status"] == "warning"

    # Cleanup
    if HANDOVER_PATH.exists():
        HANDOVER_PATH.unlink()
    for run_name in ["run_fallback_001", "run_fallback_002"]:
        run_dir = RUNS_DIR / run_name
        if run_dir.exists():
            shutil.rmtree(run_dir)


def test_import_handover_reads_file():
    """Test that import-handover reads and displays handover JSON."""
    # Create a handover file
    handover_data = {
        "handover_id": "ho_2026-07-19T12:00:00+00:00",
        "timestamp": "2026-07-19T12:00:00+00:00",
        "run_id": "run_test_20260719_120000",
        "status": "success",
        "last_successful_stage": "model_evaluation",
        "next_stage": None,
        "artifacts": [
            {"name": "model.parquet", "type": "parquet"},
            {"name": "report.pdf", "type": "pdf"},
        ],
        "error_message": None,
    }

    HANDOVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HANDOVER_PATH, "w") as f:
        json.dump(handover_data, f, indent=2)

    # Execute import-handover
    args = MagicMock()
    result = _cmd_import_handover(args)
    assert result == 0

    # Cleanup
    if HANDOVER_PATH.exists():
        HANDOVER_PATH.unlink()


def test_import_handover_missing_file():
    """Test that import-handover returns error code when file is missing."""
    # Ensure the file doesn't exist
    if HANDOVER_PATH.exists():
        HANDOVER_PATH.unlink()

    args = MagicMock()
    result = _cmd_import_handover(args)
    assert result == 1
