from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .runtime_lane_admission import inspect_target_host_archive as _base_inspector

_MAX_MATRIX_BYTES = 16 * 1024 * 1024
_POINT_CPU_EXPECTATIONS: tuple[tuple[str, Any], ...] = (
    ("forecast_mode", "point"),
    ("requested_levels", []),
    ("device", "cpu"),
    ("device_type", "cpu"),
    ("gpu_not_applicable", True),
    ("gpu_pid", None),
    ("vram_mb", None),
    ("cpu_fallback", False),
    ("n_jobs", 1),
)


def _matrix_rows(archive: Path) -> list[Mapping[str, Any]]:
    with zipfile.ZipFile(archive) as bundle:
        names = sorted(
            name for name in bundle.namelist() if name.endswith("/MODEL_RUNTIME_MATRIX.json")
        )
        if len(names) != 1:
            raise ValueError(f"expected exactly one MODEL_RUNTIME_MATRIX.json member, got {names}")
        info = bundle.getinfo(names[0])
        if info.file_size > _MAX_MATRIX_BYTES:
            raise ValueError("MODEL_RUNTIME_MATRIX.json is too large")
        payload = json.loads(bundle.read(names[0]).decode("utf-8"))
    if not isinstance(payload, list) or not all(isinstance(row, Mapping) for row in payload):
        raise ValueError("MODEL_RUNTIME_MATRIX.json must be an array of objects")
    return list(payload)


def _hardening_failures(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    failures: list[str] = []
    for row in rows:
        name = str(row.get("model_name", ""))
        for key, expected in _POINT_CPU_EXPECTATIONS:
            actual = row.get(key)
            if actual != expected:
                failures.append(f"model {name} {key}: expected {expected!r}, got {actual!r}")
    return failures


def inspect_target_host_archive(
    archive: Path | str,
    *,
    base_inspector: Callable[..., Mapping[str, Any]] = _base_inspector,
    **kwargs: Any,
) -> dict[str, Any]:
    """Apply the base admission gate and hardened point/CPU evidence checks."""

    archive_path = Path(archive)
    report = dict(base_inspector(archive_path, **kwargs))
    failures = [str(item) for item in report.get("failures", [])]
    try:
        failures.extend(_hardening_failures(_matrix_rows(archive_path)))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
        ValueError,
    ) as exc:
        failures.append(f"hardened point-certificate evidence: {exc}")
    passed = not failures
    report.update(
        {
            "status": "ADMITTED" if passed else "REJECTED",
            "decision": "RUNTIME_CERTIFIED" if passed else "MERGE_BLOCKED",
            "formal_pass": passed,
            "failures": failures,
            "point_cpu_hardening_checked": True,
        }
    )
    return report


__all__ = ["inspect_target_host_archive"]
