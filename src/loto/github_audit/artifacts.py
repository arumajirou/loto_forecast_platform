"""Integrity artifacts and ZIP packaging for GitHub audit reports."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from typing import Any

from loto.github_audit.core import iso_now, sha256_file, write_json


def package(run_dir: Path, summary: dict[str, Any]) -> str:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            files.append(
                {
                    "path": str(path.relative_to(run_dir)).replace("\\", "/"),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    write_json(
        run_dir / "ARTIFACT_MANIFEST.json",
        {
            "schema_version": 1,
            "repo": summary["repo"],
            "status": summary["status"],
            "created_at": iso_now(),
            "generator": "loto-github-audit",
            "python": sys.version,
            "read_only": True,
            "redaction": {
                "secret_values_exported": False,
                "variable_values_exported": False,
                "webhook_callback_urls_exported": False,
                "deploy_key_material_exported": False,
            },
            "files": files,
        },
    )
    sums = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            relative = str(path.relative_to(run_dir)).replace("\\", "/")
            sums.append(f"{sha256_file(path)}  {relative}")
    (run_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")

    zip_path = Path(summary["zip"])
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file():
                arcname = str(
                    Path(run_dir.name) / path.relative_to(run_dir)
                ).replace("\\", "/")
                archive.write(path, arcname)
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC verification failed at {bad}")
    digest = sha256_file(zip_path)
    zip_path.with_suffix(".zip.sha256").write_text(
        f"{digest}  {zip_path.name}\n",
        encoding="utf-8",
    )
    return digest
