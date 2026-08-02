from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from loto_ops.config import AppSettings

from .manifest import sha256_file


class ArtifactPackager:
    """Create reproducible light/full ZIP packages for an operations run."""

    _EXCLUDED_PARTS: ClassVar[set[str]] = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def _resolve_run_dir(self, run_id: str | None) -> tuple[str, Path | None]:
        runs_dir = self.settings.paths.runs_dir
        if run_id and run_id != "latest":
            candidate = runs_dir / run_id
            if not candidate.exists():
                raise FileNotFoundError(f"run directory not found: {candidate}")
            return run_id, candidate
        candidates = sorted(
            (p for p in runs_dir.glob("*") if p.is_dir()), key=lambda p: p.stat().st_mtime
        )
        if not candidates:
            return run_id or "adhoc", None
        latest = candidates[-1]
        return latest.name, latest

    @classmethod
    def _iter_files(cls, roots: Iterable[Path]) -> Iterable[tuple[Path, Path]]:
        seen: set[Path] = set()
        for root in roots:
            if not root.exists():
                continue
            if root.is_file():
                resolved = root.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield root, root.parent
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or any(part in cls._EXCLUDED_PARTS for part in path.parts):
                    continue
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield path, root.parent

    def create_zip(self, *, run_id: str | None = None, mode: str = "light") -> dict[str, object]:
        if mode not in {"light", "full"}:
            raise ValueError("mode must be 'light' or 'full'")

        resolved_run_id, run_dir = self._resolve_run_dir(run_id)
        output_dir = self.settings.paths.zip_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / f"loto_ops_{resolved_run_id}_{mode}.zip"
        manifest_path = output_dir / f"loto_ops_{resolved_run_id}_{mode}.package.json"

        roots: list[Path] = [self.settings.paths.ops_project / "configs"]
        if run_dir is not None:
            roots.append(run_dir)
        roots.extend([self.settings.paths.reports_dir])
        if mode == "full":
            roots.extend(
                [
                    self.settings.paths.datasets_dir,
                    self.settings.paths.loto_life_project / "data" / "processed",
                    self.settings.paths.loto_forecast_project / "artifacts",
                ]
            )

        files = list(self._iter_files(roots))
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for path, base in files:
                try:
                    arcname = path.relative_to(base)
                except ValueError:
                    arcname = Path(path.name)
                archive.write(path, arcname.as_posix())

        result: dict[str, object] = {
            "run_id": resolved_run_id,
            "mode": mode,
            "path": str(zip_path),
            "size_bytes": zip_path.stat().st_size,
            "sha256": sha256_file(zip_path),
            "file_count": len(files),
            "created_at": datetime.now(UTC).isoformat(),
        }
        manifest_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result["package_manifest"] = str(manifest_path)
        return result
