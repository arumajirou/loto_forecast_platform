from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_launcher() -> ModuleType:
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "run_timesfm25_runtime_certification.py"
    spec = importlib.util.spec_from_file_location("timesfm25_runtime_launcher", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _request(path: Path, snapshot: Path) -> None:
    payload = {
        "run_id": "preflight-gate-test",
        "backend": "pytorch_native",
        "repo_id": "google/timesfm-2.5-200m-pytorch",
        "revision": "1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
        "game_geometry": {
            "game_id": "test",
            "position_count": 3,
            "candidate_min": 0,
            "candidate_max": 9,
        },
        "series_ids": ["n1", "n2", "n3"],
        "history": {
            "n1": [1, 2, 3, 4],
            "n2": [2, 3, 4, 5],
            "n3": [3, 4, 5, 6],
        },
        "context_length": 4,
        "prediction_length": 1,
        "device": "cuda",
        "snapshot_path": str(snapshot.resolve()),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_failed_preflight_blocks_provider_execution(tmp_path: Path, monkeypatch: Any) -> None:
    launcher = _load_launcher()
    request_path = tmp_path / "request.json"
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _request(request_path, snapshot)
    environment = tmp_path / "environment"
    environment.mkdir()
    output_root = tmp_path / "runs"
    args = argparse.Namespace(
        project_root=tmp_path,
        request=request_path,
        output_root=output_root,
        environment=environment,
        timeout=30,
        preflight_timeout=10,
    )
    monkeypatch.setattr(
        launcher,
        "_environment_snapshot",
        lambda root: {"root": str(root)},
    )
    monkeypatch.setattr(launcher, "load_default_manifest", lambda: object())
    monkeypatch.setattr(
        launcher,
        "run_preflight",
        lambda *args, **kwargs: {
            "status": "FAIL",
            "failed_checks": ["snapshot_weight_sha256"],
        },
    )

    def provider_must_not_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("provider subprocess must not run after failed preflight")

    monkeypatch.setattr(launcher.subprocess, "run", provider_must_not_run)
    run_dir, exit_code = launcher.run_certification(args)
    assert exit_code == 1
    assert (run_dir / "preflight.json").is_file()
    assert (run_dir / "runtime_certification.json").is_file()
    assert (run_dir / "status.txt").read_text(encoding="utf-8") == "FAILED\n"
    assert not (run_dir / "command.json").exists()
    assert not (run_dir / "provider_response.json").exists()
