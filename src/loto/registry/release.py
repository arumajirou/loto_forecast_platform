from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_release_bundle(release_id: str, artifacts: list[str | Path], output_path: str | Path) -> dict:
    paths=[Path(p).resolve() for p in artifacts]
    bundle={
        "release_id":release_id,
        "created_at":datetime.now(UTC).isoformat(),
        "artifacts":[{"path":str(p),"sha256":_sha(p),"size_bytes":p.stat().st_size} for p in paths],
    }
    canonical=json.dumps(bundle,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    bundle["bundle_sha256"]=hashlib.sha256(canonical).hexdigest()
    out=Path(output_path); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding="utf-8")
    return bundle


def verify_release_bundle(bundle: dict | str | Path) -> bool:
    if not isinstance(bundle,dict):
        bundle=json.loads(Path(bundle).read_text(encoding="utf-8"))
    copy={k:v for k,v in bundle.items() if k!="bundle_sha256"}
    canonical=json.dumps(copy,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest()!=bundle.get("bundle_sha256"):
        return False
    return all(Path(a["path"]).exists() and _sha(Path(a["path"]))==a["sha256"] for a in bundle["artifacts"])
