from __future__ import annotations

import importlib.metadata as metadata
from typing import Any


MLFORECAST_REQUIRED_VERSION = "1.1.0"
MLFORECAST_UPSTREAM_TAG = "v1.1.0"
MLFORECAST_UPSTREAM_COMMIT = "a1609efddf8cf1a83510a50cd5487b66f32271c6"
MLFORECAST_WHEEL_SHA256 = "0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748"


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
