from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.mlforecast.certify import _prediction_check, verify_wheel_file


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
    prediction = pd.DataFrame(
        {"unique_id": ["p1", "p2"], "ds": [1, 1], "ridge": [1.0, np.nan]}
    )
    with pytest.raises(RuntimeError, match="non-finite"):
        _prediction_check(prediction, column="ridge", expected_rows=2)
