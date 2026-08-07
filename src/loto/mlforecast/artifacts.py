from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from loto.mlforecast.provenance import upstream_contract


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _canonical_frame_hash(
    frame: pd.DataFrame,
    *,
    id_col: str,
    time_col: str,
) -> str:
    ordered = frame.sort_values([id_col, time_col]).reset_index(drop=True)
    payload = ordered.to_csv(index=False, lineterminator="\n").encode()
    return sha256_bytes(payload)


def _package_versions() -> dict[str, str | None]:
    packages = (
        "mlforecast",
        "coreforecast",
        "utilsforecast",
        "optuna",
        "scikit-learn",
        "lightgbm",
        "xgboost",
        "catboost",
        "pandas",
        "numpy",
    )
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _environment() -> dict[str, Any]:
    git_commit = os.getenv("GITHUB_SHA")
    if git_commit is None:
        try:
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            git_commit = None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "git_commit": git_commit,
        "packages": _package_versions(),
        "mlforecast_upstream": upstream_contract(),
    }


def _write_manifest(run_dir: Path) -> None:
    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    records = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name in excluded:
            continue
        records.append(
            {
                "path": path.relative_to(run_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    atomic_write_text(
        run_dir / "ARTIFACT_MANIFEST.json",
        json.dumps({"artifacts": records}, indent=2, sort_keys=True) + "\n",
    )
    sums = "".join(f"{record['sha256']}  {record['path']}\n" for record in records)
    atomic_write_text(run_dir / "SHA256SUMS", sums)
