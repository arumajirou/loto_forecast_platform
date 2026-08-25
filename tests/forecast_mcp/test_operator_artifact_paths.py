from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.forecast_mcp.contracts import (
    APPROVED_REQUEST_NAME,
    REQUEST_MANIFEST_NAME,
    Moirai2RouteConfig,
)


def _base(tmp_path: Path) -> dict[str, object]:
    return {
        "repo_root": tmp_path,
        "provider_python": tmp_path / "python",
        "provider_script": tmp_path / "run_moirai2_provider.py",
        "runtime_lane": "cuda13-experimental",
    }


def _json_base(tmp_path: Path) -> dict[str, object]:
    return {
        "repo_root": str(tmp_path),
        "provider_python": str(tmp_path / "python"),
        "provider_script": str(tmp_path / "run_moirai2_provider.py"),
        "runtime_lane": "cuda13-experimental",
    }


def test_operator_runtime_root_derives_canonical_pair(tmp_path: Path) -> None:
    route_root = tmp_path / "operator-route"
    route = Moirai2RouteConfig(
        **_base(tmp_path),
        operator_runtime_root=route_root,
    )

    assert route.operator_runtime_root == route_root
    assert route.approved_request == route_root / APPROVED_REQUEST_NAME
    assert route.request_manifest == route_root / REQUEST_MANIFEST_NAME


def test_operator_runtime_root_accepts_json_mode(tmp_path: Path) -> None:
    route_root = tmp_path / "operator-route"
    payload = {
        **_json_base(tmp_path),
        "operator_runtime_root": str(route_root),
    }

    route = Moirai2RouteConfig.model_validate_json(json.dumps(payload))

    assert route.operator_runtime_root == route_root
    assert route.approved_request == route_root / APPROVED_REQUEST_NAME
    assert route.request_manifest == route_root / REQUEST_MANIFEST_NAME


def test_legacy_pair_is_normalized_to_one_runtime_root(tmp_path: Path) -> None:
    route_root = tmp_path / "legacy-route"
    route = Moirai2RouteConfig(
        **_base(tmp_path),
        approved_request=route_root / APPROVED_REQUEST_NAME,
        request_manifest=route_root / REQUEST_MANIFEST_NAME,
    )

    dumped = route.model_dump(mode="json")
    assert route.operator_runtime_root == route_root
    assert dumped["operator_runtime_root"] == str(route_root)
    assert "approved_request" not in dumped
    assert "request_manifest" not in dumped


def test_legacy_pair_accepts_json_mode(tmp_path: Path) -> None:
    route_root = tmp_path / "legacy-route"
    payload = {
        **_json_base(tmp_path),
        "approved_request": str(route_root / APPROVED_REQUEST_NAME),
        "request_manifest": str(route_root / REQUEST_MANIFEST_NAME),
    }

    route = Moirai2RouteConfig.model_validate_json(json.dumps(payload))

    assert route.operator_runtime_root == route_root


def test_legacy_pair_path_drift_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="path drift"):
        Moirai2RouteConfig(
            **_base(tmp_path),
            approved_request=tmp_path / "old" / APPROVED_REQUEST_NAME,
            request_manifest=tmp_path / "new" / REQUEST_MANIFEST_NAME,
        )


def test_root_conflicting_with_legacy_pair_is_rejected(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    with pytest.raises(ValidationError, match="conflicts"):
        Moirai2RouteConfig(
            **_base(tmp_path),
            operator_runtime_root=tmp_path / "canonical",
            approved_request=legacy_root / APPROVED_REQUEST_NAME,
            request_manifest=legacy_root / REQUEST_MANIFEST_NAME,
        )


def test_noncanonical_legacy_filename_is_rejected(tmp_path: Path) -> None:
    route_root = tmp_path / "legacy"
    with pytest.raises(ValidationError, match="filename is not canonical"):
        Moirai2RouteConfig(
            **_base(tmp_path),
            approved_request=route_root / "request.json",
            request_manifest=route_root / REQUEST_MANIFEST_NAME,
        )
