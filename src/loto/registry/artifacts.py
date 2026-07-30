from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


class ArtifactStore:
    """Content-addressed local artifact store with immutable writes."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def put_file(self, path: str | Path, *, namespace: str = "default") -> dict:
        source = Path(path)
        digest = self.sha256(source)
        target = self.root / namespace / digest[:2] / digest / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(source, tmp)
            tmp.replace(target)
        return {"uri": target.resolve().as_uri(), "sha256": digest, "size": source.stat().st_size}

    def put_json(self, payload: dict, name: str, *, namespace: str = "default") -> dict:
        tmp = self.root / ".tmp" / name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        result = self.put_file(tmp, namespace=namespace)
        tmp.unlink(missing_ok=True)
        return result
