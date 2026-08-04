"""Ray worker/driver code-hash comparison tests.

The standing directive requires per-file SHA-256 evidence (of exactly
`runner.py`, `trial_persistence.py`, `p1_compat.py`, `persistence.py`) plus
installed-package identity (NeuralForecast/Ray/Torch versions) captured on
both the driver and the Ray/Optuna worker, with any mismatch treated as a
formal FAIL. Process/path fields (PID, CUDA_VISIBLE_DEVICES, python
executable, sys.path, loto package path) are captured for audit only, since
they are guaranteed to differ from the driver under normal worker execution.
These tests exercise the real hashing/comparison logic against this
repository's actual files -- no mocking of the hash computation itself.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from loto.auto_campaign.runtime import (
    CODE_FINGERPRINT_FILES,
    code_environment_fingerprint,
    compare_code_fingerprints,
)


def test_code_environment_fingerprint_hashes_match_real_files_on_disk() -> None:
    fingerprint = code_environment_fingerprint()
    package_dir = Path(__file__).resolve().parents[2] / "src" / "loto" / "auto_campaign"

    assert set(fingerprint["file_sha256"]) == set(CODE_FINGERPRINT_FILES)
    for name in CODE_FINGERPRINT_FILES:
        expected = hashlib.sha256((package_dir / name).read_bytes()).hexdigest()
        assert fingerprint["file_sha256"][name] == expected

    assert fingerprint["loto_package_path"].endswith("__init__.py")
    assert fingerprint["python_executable"]
    assert isinstance(fingerprint["sys_path"], list)
    assert fingerprint["pid"] > 0


def test_compare_code_fingerprints_passes_when_identical() -> None:
    fingerprint = code_environment_fingerprint()
    result = compare_code_fingerprints(fingerprint, fingerprint)
    assert result["status"] == "PASS"
    assert result["mismatches"] == []


def test_compare_code_fingerprints_fails_on_file_hash_divergence() -> None:
    driver = code_environment_fingerprint()
    worker = code_environment_fingerprint()
    worker["file_sha256"]["runner.py"] = "0" * 64

    result = compare_code_fingerprints(driver, worker)

    assert result["status"] == "FAIL"
    assert "file_sha256[runner.py]" in result["mismatches"]


def test_compare_code_fingerprints_fails_on_version_divergence() -> None:
    driver = code_environment_fingerprint()
    worker = code_environment_fingerprint()
    worker["ray_version"] = "0.0.0-does-not-match"

    result = compare_code_fingerprints(driver, worker)

    assert result["status"] == "FAIL"
    assert "ray_version" in result["mismatches"]


def test_compare_code_fingerprints_ignores_pid_and_cuda_visible_devices() -> None:
    """A worker is, by construction, a different process -- PID must always
    differ, and Ray may legitimately assign a different CUDA_VISIBLE_DEVICES
    per trial actor. Neither should ever gate the mismatch/FAIL decision.
    """

    driver = code_environment_fingerprint()
    worker = code_environment_fingerprint()
    worker["pid"] = driver["pid"] + 1
    worker["cuda_visible_devices"] = "does-not-match"

    result = compare_code_fingerprints(driver, worker)

    assert result["status"] == "PASS"
    assert result["mismatches"] == []


def test_compare_code_fingerprints_ignores_ray_working_dir_staging_paths() -> None:
    """Under the Ray backend, `runtime_env.working_dir` stages a
    session-specific copy of the project into a temp directory before
    launching the worker, so `python_executable`, `sys_path`, and
    `loto_package_path` are guaranteed to differ from the driver's even when
    the worker runs byte-identical code from a byte-identical package
    install. None of the three should gate the mismatch/FAIL decision.
    """

    driver = code_environment_fingerprint()
    worker = code_environment_fingerprint()
    worker["python_executable"] = "/tmp/ray_pkg_xyz/.venv/bin/python"
    worker["sys_path"] = ["/tmp/ray_pkg_xyz", *worker["sys_path"]]
    worker["loto_package_path"] = "/tmp/ray_pkg_xyz/src/loto/__init__.py"

    result = compare_code_fingerprints(driver, worker)

    assert result["status"] == "PASS"
    assert result["mismatches"] == []
