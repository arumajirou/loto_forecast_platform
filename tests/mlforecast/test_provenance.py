from __future__ import annotations

import importlib.metadata as metadata

import pytest

from loto.mlforecast.provenance import (
    MLFORECAST_REQUIRED_VERSION,
    MLFORECAST_UPSTREAM_COMMIT,
    verify_mlforecast_runtime,
)


def test_runtime_version_exact_match(monkeypatch) -> None:
    monkeypatch.setattr(metadata, "version", lambda package: "1.0.31")
    result = verify_mlforecast_runtime()
    assert result["installed_version"] == MLFORECAST_REQUIRED_VERSION
    assert result["upstream_commit"] == MLFORECAST_UPSTREAM_COMMIT


def test_runtime_version_mismatch_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(metadata, "version", lambda package: "1.0.30")
    with pytest.raises(RuntimeError, match="version mismatch"):
        verify_mlforecast_runtime()


def test_missing_runtime_fails_closed(monkeypatch) -> None:
    def missing(package: str) -> str:
        raise metadata.PackageNotFoundError(package)

    monkeypatch.setattr(metadata, "version", missing)
    with pytest.raises(RuntimeError, match="not installed"):
        verify_mlforecast_runtime()
