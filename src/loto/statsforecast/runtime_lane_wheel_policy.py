from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .runtime_lane_artifacts import (
    prepare_offline_bundle as _prepare_offline_bundle,
)
from .runtime_lane_artifacts import (
    verify_offline_bundle as _verify_offline_bundle,
)


def verify_offline_bundle(wheelhouse: Path) -> dict[str, Any]:
    report = _verify_offline_bundle(wheelhouse)
    failures = list(report["failures"])
    selection_path = wheelhouse / "PYPI_RELEASE_SELECTION.json"
    if selection_path.is_file():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        filename = str(selection.get("selected", {}).get("filename", ""))
        if not filename.endswith(".whl"):
            failures.append("selected StatsForecast artifact is not a wheel")
    return {
        "status": "PASS" if not failures else "FAILED",
        "failures": failures,
        "verified": report["verified"],
    }


def prepare_offline_bundle(
    repo_root: Path,
    wheelhouse: Path,
    *,
    uv_executable: str = "uv",
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    previous = os.environ.get("PIP_ONLY_BINARY")
    os.environ["PIP_ONLY_BINARY"] = ":all:"
    try:
        bundle = _prepare_offline_bundle(
            repo_root,
            wheelhouse,
            uv_executable=uv_executable,
            opener=opener,
        )
    finally:
        if previous is None:
            os.environ.pop("PIP_ONLY_BINARY", None)
        else:
            os.environ["PIP_ONLY_BINARY"] = previous
    report = verify_offline_bundle(bundle)
    if report["status"] != "PASS":
        raise RuntimeError(f"wheel-only offline bundle verification failed: {report['failures']}")
    return bundle


__all__ = ["prepare_offline_bundle", "verify_offline_bundle"]
