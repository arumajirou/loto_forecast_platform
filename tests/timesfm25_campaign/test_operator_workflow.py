from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from loto.timesfm25_campaign.certification_bundle import sha256_file
from loto.timesfm25_campaign.operator_workflow import (
    build_runner_script,
    create_deterministic_zip,
    create_request_payload,
    default_run_id,
    inspect_runtime_bundle,
    tmux_launch_command,
    tmux_session_name,
)


def _template(path: Path) -> Path:
    payload = {
        "schema_version": 2,
        "run_id": "placeholder",
        "backend": "pytorch_native",
        "local_files_only": True,
        "device": "cpu",
        "snapshot_path": None,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _seal(root: Path, files: dict[str, str]) -> None:
    lines = []
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        lines.append(f"{sha256_file(path)}  {relative}")
    (root / "SHA256SUMS").write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")


def test_default_run_id_is_stable_for_supplied_time() -> None:
    now = datetime(2026, 8, 6, 1, 2, 3, tzinfo=UTC)
    assert default_run_id(now) == "timesfm25-native-20260806T010203Z"


def test_tmux_session_name_is_safe() -> None:
    assert tmux_session_name("run_1.2") == "tfm25-run-1-2"


def test_long_tmux_session_names_keep_unique_hash_suffix() -> None:
    first = tmux_session_name("a" * 128)
    second = tmux_session_name("a" * 127 + "b")
    assert len(first) == 120
    assert len(second) == 120
    assert first != second


def test_create_request_updates_runtime_fields(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    payload = create_request_payload(
        _template(tmp_path / "template.json"),
        run_id="run-1",
        snapshot_path=snapshot,
    )
    assert payload["run_id"] == "run-1"
    assert payload["snapshot_path"] == str(snapshot)
    assert payload["device"] == "cuda"


def test_create_request_rejects_relative_snapshot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        create_request_payload(
            _template(tmp_path / "template.json"),
            run_id="run-1",
            snapshot_path=Path("relative"),
        )


def test_runner_script_enforces_offline_execution(tmp_path: Path) -> None:
    script = build_runner_script(
        project_root=tmp_path,
        request_path=tmp_path / "request.json",
        environment=tmp_path / "environment",
        output_root=tmp_path / "runs",
        control_dir=tmp_path / "operator",
        timeout=60,
        preflight_timeout=30,
    )
    assert "HF_HUB_OFFLINE=1" in script
    assert "UV_OFFLINE=1" in script
    assert "run_timesfm25_runtime_certification.py" in script
    assert "--preflight-timeout 30" in script
    assert "--timeout 60" in script


def test_tmux_command_uses_argument_vector(tmp_path: Path) -> None:
    command = tmux_launch_command("tfm25-run-1", tmp_path / "runner.sh")
    assert command[:6] == ["tmux", "new-session", "-d", "-s", "tfm25-run-1", "bash"]


def test_inspect_runtime_reports_running(tmp_path: Path) -> None:
    summary = inspect_runtime_bundle(tmp_path / "run", tmux_alive=True)
    assert summary["operator_status"] == "RUNNING"


def test_inspect_runtime_reports_partial_for_valid_bundle(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _seal(
        run_dir,
        {
            "status.txt": "PARTIALLY_VERIFIED_GPU\n",
            "runtime_certification.json": '{"runtime_status":"PARTIALLY_VERIFIED_GPU"}\n',
        },
    )
    summary = inspect_runtime_bundle(run_dir, tmux_alive=False)
    assert summary["operator_status"] == "PARTIAL"
    assert summary["manifest_ok"] is True


def test_deterministic_zip_has_stable_hash(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    _seal(run_dir, {"status.txt": "VERIFIED_GPU\n", "result.json": "{}\n"})
    first = create_deterministic_zip(run_dir, tmp_path / "one.zip")
    second = create_deterministic_zip(run_dir, tmp_path / "two.zip")
    assert first["sha256"] == second["sha256"]
    with zipfile.ZipFile(first["archive_path"]) as archive:
        assert archive.namelist() == [
            "run-1/SHA256SUMS",
            "run-1/result.json",
            "run-1/status.txt",
        ]


def test_archive_rejects_tampered_bundle(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _seal(run_dir, {"status.txt": "VERIFIED_GPU\n"})
    (run_dir / "status.txt").write_text("FAILED\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not sealed"):
        create_deterministic_zip(run_dir, tmp_path / "run.zip")


def test_archive_must_be_outside_bundle(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _seal(run_dir, {"status.txt": "VERIFIED_GPU\n"})
    with pytest.raises(ValueError, match="outside"):
        create_deterministic_zip(run_dir, run_dir / "archive.zip")
