from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from loto.basicts_campaign.orchestration import (
    CommandExecutionError,
    OrchestrationError,
    _prepare_requests,
    _prepared_lock_sha256,
    _run_checked,
    _safe_run_id,
    _write_portable_bundle,
)


def test_prepare_requests_rewrites_only_output_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config_dir = repo_root / "configs" / "basicts_campaign"
    config_dir.mkdir(parents=True)
    operations = {
        "identity.json": "identity",
        "validate_config.json": "validate_config",
        "dlinear_smoke.json": "dlinear_smoke",
    }
    for filename, operation in operations.items():
        (config_dir / filename).write_text(
            json.dumps({"operation": operation, "output_dir": "old", "seed": 1}),
            encoding="utf-8",
        )
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    prepared = _prepare_requests(repo_root, run_dir)

    assert set(prepared) == set(operations.values())
    for operation, path in prepared.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["operation"] == operation
        assert payload["output_dir"] == str(run_dir / operation)
        source = config_dir / next(
            filename for filename, value in operations.items() if value == operation
        )
        assert json.loads(source.read_text(encoding="utf-8"))["output_dir"] == "old"


def test_run_checked_captures_stdout_and_stderr(tmp_path: Path) -> None:
    result = _run_checked(
        phase="probe",
        command=(
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr)",
        ),
        cwd=tmp_path,
        env=os.environ.copy(),
        log_dir=tmp_path,
        timeout_seconds=30,
    )

    assert result.returncode == 0
    assert Path(result.stdout_path).read_text(encoding="utf-8") == "out\n"
    assert Path(result.stderr_path).read_text(encoding="utf-8") == "err\n"


def test_run_checked_fails_closed_and_retains_result(tmp_path: Path) -> None:
    with pytest.raises(CommandExecutionError, match="returncode=7") as caught:
        _run_checked(
            phase="failure",
            command=(
                sys.executable,
                "-c",
                "import sys; print('failure', file=sys.stderr); raise SystemExit(7)",
            ),
            cwd=tmp_path,
            env=os.environ.copy(),
            log_dir=tmp_path,
            timeout_seconds=30,
        )

    assert caught.value.result.returncode == 7
    assert (tmp_path / "failure.stderr.log").read_text(encoding="utf-8") == "failure\n"


def test_portable_bundle_hashes_nested_files(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "evidence.txt").write_text("evidence\n", encoding="utf-8")

    _write_portable_bundle(
        tmp_path,
        {"schema_version": "1.0", "status": "FAILED", "run_id": "run-1"},
    )

    manifest = json.loads(
        (tmp_path / "P0_RUN_MANIFEST.json").read_text(encoding="utf-8")
    )
    paths = {entry["path"] for entry in manifest["files"]}
    assert "nested/evidence.txt" in paths
    checksum_lines = (tmp_path / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    expected_digest = hashlib.sha256(b"evidence\n").hexdigest()
    assert f"{expected_digest}  nested/evidence.txt" in checksum_lines


def test_portable_bundle_rejects_symbolic_links(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("target\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(OrchestrationError, match="symbolic links are forbidden"):
        _write_portable_bundle(
            tmp_path,
            {"schema_version": "1.0", "status": "FAILED", "run_id": "run-1"},
        )


def test_prepared_lock_sha256_accepts_matching_formal_audit(tmp_path: Path) -> None:
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("lock\n", encoding="utf-8")
    digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    artifacts_root = tmp_path / "formal"
    preflight = artifacts_root / "preflight"
    preflight.mkdir(parents=True)
    (preflight / "UV_RESOLUTION_AUDIT.json").write_text(
        json.dumps({"status": "PASS", "lockfile": {"sha256": digest}}),
        encoding="utf-8",
    )

    assert _prepared_lock_sha256(artifacts_root, lockfile) == digest


def test_prepared_lock_sha256_rejects_lock_drift(tmp_path: Path) -> None:
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("before\n", encoding="utf-8")
    digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    artifacts_root = tmp_path / "formal"
    preflight = artifacts_root / "preflight"
    preflight.mkdir(parents=True)
    (preflight / "UV_RESOLUTION_AUDIT.json").write_text(
        json.dumps({"status": "PASS", "lockfile": {"sha256": digest}}),
        encoding="utf-8",
    )
    lockfile.write_text("after\n", encoding="utf-8")

    with pytest.raises(OrchestrationError, match="changed after formal preflight"):
        _prepared_lock_sha256(artifacts_root, lockfile)


@pytest.mark.parametrize("value", ["../escape", "with space", "", "slash/name"])
def test_safe_run_id_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(OrchestrationError):
        _safe_run_id(value)
