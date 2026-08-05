from __future__ import annotations

import importlib.metadata as metadata
from typing import Any


MLFORECAST_REQUIRED_VERSION = "1.0.31"
MLFORECAST_UPSTREAM_TAG = "v1.0.31"
MLFORECAST_UPSTREAM_COMMIT = "c8f8b6d25184dcbed2454e185a92f3f8ef2e17e8"
MLFORECAST_WHEEL_SHA256 = "941c4623f3440e0c3fa63db9df0a9ad198045cdb04bd624c8188edd11c74a441"


def upstream_contract() -> dict[str, Any]:
    return {
        "package": "mlforecast",
        "required_version": MLFORECAST_REQUIRED_VERSION,
        "upstream_tag": MLFORECAST_UPSTREAM_TAG,
        "upstream_commit": MLFORECAST_UPSTREAM_COMMIT,
        "wheel_sha256": MLFORECAST_WHEEL_SHA256,
    }


def verify_mlforecast_runtime(
    expected_version: str = MLFORECAST_REQUIRED_VERSION,
) -> dict[str, Any]:
    try:
        installed_version = metadata.version("mlforecast")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"mlforecast=={expected_version} is required but is not installed"
        ) from exc
    if installed_version != expected_version:
        raise RuntimeError(
            "MLForecast runtime version mismatch: "
            f"expected={expected_version}, installed={installed_version}"
        )
    return upstream_contract() | {"installed_version": installed_version}
