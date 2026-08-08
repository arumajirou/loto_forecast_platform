from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.basicts_campaign.formal_orchestration import (
    FormalP0Error,
    _copy_json_stdout,
    _uv_version,
    _write_formal_bundle,
)
from loto.basicts_campaign.orchestration import CommandResult


def _result(tmp_path: Path, stdout: str, phase: str = "probe") -> CommandResult:
    stdout_path = tmp_path / f"{phase}.stdout.log"
    stderr_path = tmp_path / f"{phase}.stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return CommandResult(
        phase=phase,
        command=("uv",),
        returncode=0,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def test_uv_version_accepts_frozen_version(tmp_path: Path) -> None:
    assert _uv_version(_result(tmp_path, "uv 0.12.0\n")) == "0.12.0"


def test_uv_version_rejects_drift(tmp_path: Path) -> None:
    with pytest.raises(FormalP0Error, match="uv version mismatch"):
        _uv_version(_result(tmp_path, "uv 0.12.1\n"))


def test_copy_json_stdout_requires_object(tmp_path: Path) -> None:
    destination = tmp_path / "metadata.json"
    with pytest.raises(FormalP0Error, match="must contain an object"):
        _copy_json_stdout(_result(tmp_path, "[]\n"), destination)


def test_copy_json_stdout_writes_canonical_json(tmp_path: Path) -> None:
    destination = tmp_path / "metadata.json"
    _copy_json_stdout(_result(tmp_path, '{"b": 2, "a": 1}\n'), destination)

    assert json.loads(destination.read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_write_formal_bundle_hashes_nested_evidence(tmp_path: Path) -> None:
    nested = tmp_path / "core"
    nested.mkdir()
    (nested / "evidence.json").write_text("{}\n", encoding="utf-8")

    _write_formal_bundle(
        tmp_path,
        {"schema_version": "1.0", "status": "FAILED", "run_id": "run-1"},
    )

    manifest = json.loads((tmp_path / "FORMAL_P0_MANIFEST.json").read_text(encoding="utf-8"))
    assert "core/evidence.json" in {item["path"] for item in manifest["files"]}
    assert (tmp_path / "SHA256SUMS").is_file()
