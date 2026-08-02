from __future__ import annotations

from pathlib import Path

from loto_ops.config import load_settings


def list_artifacts() -> list[Path]:
    settings = load_settings()
    files: list[Path] = []
    for base in [
        settings.paths.reports_dir,
        settings.paths.datasets_dir,
        settings.paths.zip_output_dir,
    ]:
        if base.exists():
            files.extend([p for p in base.rglob("*") if p.is_file()])
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
