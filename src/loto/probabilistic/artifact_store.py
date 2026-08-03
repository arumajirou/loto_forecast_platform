from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ProbabilisticArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe(self, relative: str | Path) -> Path:
        target = (self.root / relative).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"path traversal rejected: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def write_json(self, relative: str | Path, payload: Any) -> Path:
        target = self._safe(relative)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return target

    def write_yaml(self, relative: str | Path, payload: Any) -> Path:
        target = self._safe(relative)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        os.replace(temporary, target)
        return target

    def write_table(self, relative: str | Path, frame: pd.DataFrame) -> Path:
        target = self._safe(relative)
        temporary = target.with_suffix(target.suffix + ".tmp")
        if target.suffix.lower() == ".parquet":
            try:
                frame.to_parquet(temporary, index=False)
            except Exception:
                target = target.with_suffix(".csv")
                temporary = target.with_suffix(".csv.tmp")
                frame.to_csv(temporary, index=False)
        else:
            frame.to_csv(temporary, index=False)
        os.replace(temporary, target)
        return target

    def manifest(self, *, metadata: dict[str, Any] | None = None) -> Path:
        files = []
        for path in sorted(p for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(".tmp")):
            if path.name == "SHA256SUMS.json":
                continue
            files.append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        return self.write_json(
            "SHA256SUMS.json", {"schema_version": 1, "metadata": metadata or {}, "files": files}
        )
