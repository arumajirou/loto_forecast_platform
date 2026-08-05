"""Prediction-lock-aware verification for portable artifact bundles."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .portable_artifact import (
    PORTABLE_MANIFEST,
    _safe_extract_zip,
    verify_portable_bundle,
)
from .prediction_lock import verify_prediction_lock


def _safe_target_path(value: Any) -> Path:
    text = str(value or "")
    if "\\" in text:
        raise ValueError("portable target path contains a backslash")
    pure = PurePosixPath(text)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts or "." in pure.parts:
        raise ValueError(f"portable target path is unsafe: {text}")
    return Path(*pure.parts)


def _verify_extracted_prediction_lock(root: Path) -> dict[str, Any]:
    manifest_path = root / PORTABLE_MANIFEST
    try:
        portable = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "failures": [
                f"portable prediction verification cannot read manifest: "
                f"{type(exc).__name__}: {exc}"
            ],
        }
    if not isinstance(portable, dict):
        return {
            "status": "FAIL",
            "failures": ["portable manifest must be a JSON object"],
        }
    try:
        relative = _safe_target_path(portable.get("target_relative_path"))
        target = (root / relative).resolve(strict=True)
        target.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        return {
            "status": "FAIL",
            "failures": [
                f"portable target cannot be resolved safely: "
                f"{type(exc).__name__}: {exc}"
            ],
        }
    manifest_file = target / "manifest.json"
    try:
        run_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "failures": [
                f"portable target manifest unreadable: {type(exc).__name__}: {exc}"
            ],
        }
    if not isinstance(run_manifest, dict):
        return {
            "status": "FAIL",
            "failures": ["portable target manifest must be a JSON object"],
        }
    return verify_prediction_lock(target, run_manifest)


def verify_portable_bundle_with_prediction_lock(bundle: Path) -> dict[str, Any]:
    """Run portable verification and re-evaluate the relocated prediction lock."""

    bundle = bundle.resolve()
    base = verify_portable_bundle(bundle)
    if base.get("status") != "PASS":
        return {
            **base,
            "prediction_lock_verification": {
                "status": "NOT_RUN_BASE_PORTABLE_FAILED",
                "failures": [],
            },
        }

    try:
        if bundle.is_dir():
            prediction = _verify_extracted_prediction_lock(bundle)
        else:
            with tempfile.TemporaryDirectory(prefix="verify-portable-prediction-") as value:
                root = Path(value)
                _safe_extract_zip(bundle, root)
                prediction = _verify_extracted_prediction_lock(root)
    except (OSError, ValueError) as exc:
        prediction = {
            "status": "FAIL",
            "failures": [
                f"portable prediction verification failed: "
                f"{type(exc).__name__}: {exc}"
            ],
        }

    failures = list(base.get("failures") or [])
    failures.extend(
        f"prediction-lock:{failure}"
        for failure in prediction.get("failures", [])
    )
    return {
        **base,
        "status": "PASS" if not failures and prediction.get("status") in {
            "PASS",
            "NOT_APPLICABLE",
        } else "FAIL",
        "prediction_lock_verification": prediction,
        "failures": failures,
    }
