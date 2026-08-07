from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_timesfm25_target_host.py"
    spec = importlib.util.spec_from_file_location("run_timesfm25_target_host", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_supports_launch_status_and_finalize() -> None:
    module = _load_script()
    parser = module.build_parser()
    launch = parser.parse_args(["launch", "--snapshot", "/tmp/snapshot"])
    status = parser.parse_args(["status", "--run-id", "run-1"])
    finalize = parser.parse_args(["finalize", "--run-id", "run-1"])
    assert launch.handler is module.launch
    assert status.handler is module.status
    assert finalize.handler is module.finalize


def test_preflight_command_adds_generate_lock(tmp_path: Path) -> None:
    module = _load_script()
    parser = module.build_parser()
    args = parser.parse_args(
        [
            "launch",
            "--snapshot",
            str(tmp_path / "snapshot"),
            "--project-root",
            str(tmp_path),
            "--generate-lock",
        ]
    )
    command = module._preflight_command(
        args,
        tmp_path / "request.json",
        tmp_path / "preflight.json",
    )
    assert command[-1] == "--generate-lock"
    assert "prepare_timesfm25_runtime.py" in " ".join(command)


def test_launch_rejects_invalid_run_id_before_writing(tmp_path: Path) -> None:
    module = _load_script()
    parser = module.build_parser()
    args = parser.parse_args(
        [
            "launch",
            "--snapshot",
            str(tmp_path / "snapshot"),
            "--run-id",
            "../escape",
            "--operator-root",
            str(tmp_path / "operator"),
            "--foreground",
        ]
    )
    with pytest.raises(ValueError, match="run_id"):
        module.launch(args)
    assert not (tmp_path / "operator").exists()
