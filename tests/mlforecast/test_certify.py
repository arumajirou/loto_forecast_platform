from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.mlforecast.certify import (
    _assert_prediction_keys_match,
    _prediction_check,
    _thread_environment,
    _validate_trial_completion,
    _validated_prediction_keys,
    verify_wheel_file,
)


def _fake_wheel(path: Path, *, version: str = "1.1.0") -> str:
    metadata = f"Name: mlforecast\nVersion: {version}\n\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mlforecast-1.1.0.dist-info/METADATA", metadata)
        archive.writestr("mlforecast/__init__.py", "__version__ = '1.1.0'\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verify_wheel_file_checks_hash_and_metadata(tmp_path: Path) -> None:
    wheel = tmp_path / "mlforecast-1.1.0-py3-none-any.whl"
    digest = _fake_wheel(wheel)
    result = verify_wheel_file(wheel, expected_sha256=digest)
    assert result["verified"] is True
    assert result["metadata_version"] == "1.1.0"


def test_verify_wheel_file_rejects_hash_mismatch(tmp_path: Path) -> None:
    wheel = tmp_path / "mlforecast-1.1.0-py3-none-any.whl"
    _fake_wheel(wheel)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify_wheel_file(wheel, expected_sha256="0" * 64)


def test_verify_wheel_file_rejects_version_mismatch(tmp_path: Path) -> None:
    wheel = tmp_path / "mlforecast-1.1.0-py3-none-any.whl"
    digest = _fake_wheel(wheel, version="1.0.31")
    with pytest.raises(RuntimeError, match="metadata mismatch"):
        verify_wheel_file(wheel, expected_sha256=digest)


def test_prediction_check_rejects_nonfinite_values() -> None:
    prediction = pd.DataFrame({"unique_id": ["p1", "p2"], "ds": [1, 1], "ridge": [1.0, np.nan]})
    with pytest.raises(RuntimeError, match="non-finite"):
        _prediction_check(prediction, column="ridge", expected_rows=2)


def test_prediction_keys_reject_duplicates() -> None:
    prediction = pd.DataFrame({"unique_id": ["p1", "p1"], "ds": [1, 1], "ridge": [1.0, 1.0]})
    with pytest.raises(RuntimeError, match="duplicate prediction keys"):
        _validated_prediction_keys(prediction)


def test_thread_environment_requires_all_variables(monkeypatch) -> None:
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "1")
    result = _thread_environment()
    assert set(result.values()) == {"1"}


def test_thread_environment_rejects_non_single_thread(monkeypatch) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    monkeypatch.setenv("MKL_NUM_THREADS", "1")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "1")
    monkeypatch.setenv("NUMEXPR_NUM_THREADS", "1")
    with pytest.raises(RuntimeError, match="single-thread runtime contract"):
        _thread_environment()


class _State:
    def __init__(self, name: str) -> None:
        self.name = name


class _Trial:
    def __init__(self, state: str) -> None:
        self.state = _State(state)


class _Study:
    def __init__(self, states: list[str], best_value: float = 0.1) -> None:
        self.trials = [_Trial(state) for state in states]
        self.best_value = best_value


def test_prediction_key_match_rejects_different_keys() -> None:
    before = pd.DataFrame({"unique_id": ["p1", "p2"], "ds": [1, 1], "ridge": [1.0, 2.0]})
    after = pd.DataFrame({"unique_id": ["p1", "p2"], "ds": [1, 2], "ridge": [1.0, 2.0]})
    with pytest.raises(RuntimeError, match="prediction key mismatch"):
        _assert_prediction_keys_match(before, after)


def test_trial_completion_requires_every_requested_trial() -> None:
    with pytest.raises(RuntimeError, match="trial contract failed"):
        _validate_trial_completion(_Study(["COMPLETE", "FAIL"]), 2)


def test_trial_completion_accepts_all_complete_trials() -> None:
    result = _validate_trial_completion(_Study(["COMPLETE", "COMPLETE"]), 2)
    assert result == {"observed_trials": 2, "complete_trials": 2}
