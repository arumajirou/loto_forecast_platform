from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loto.merlion_campaign.provenance import (
    PACKAGE_VERSION,
    UPSTREAM_REVISION,
    sha256_file,
)

MANIFEST_NAME = "MODEL_ARTIFACT_MANIFEST.json"


def resolve_under(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if target == root or root not in target.parents:
        raise ValueError("artifact path escapes work root")
    return target


def build_model_manifest(
    model_dir: Path,
    *,
    request_id: str,
    model_name: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    files = []
    for path in sorted(model_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError("model artifact must not contain symbolic links")
        if path.is_file() and path.name != MANIFEST_NAME:
            files.append(
                {
                    "path": path.relative_to(model_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    if not files:
        raise ValueError("model artifact is empty")
    manifest = {
        "schema_version": "merlion-model-artifact-v1",
        "request_id": request_id,
        "model_name": model_name,
        "config": config,
        "files": files,
        "package_version": PACKAGE_VERSION,
        "upstream_revision": UPSTREAM_REVISION,
        "trust_scope": "caller_controlled_work_root",
    }
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    manifest_sha = hashlib.sha256(canonical).hexdigest()
    manifest["manifest_sha256"] = manifest_sha
    (model_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest, manifest_sha


def verify_model_manifest(model_dir: Path, expected_sha256: str) -> dict[str, Any]:
    manifest_path = model_dir / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("trusted model manifest is missing or unsafe")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed = manifest.pop("manifest_sha256", None)
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    actual_manifest_sha = hashlib.sha256(canonical).hexdigest()
    if claimed != actual_manifest_sha or expected_sha256 != actual_manifest_sha:
        raise ValueError("model manifest hash mismatch")
    if manifest.get("package_version") != PACKAGE_VERSION:
        raise ValueError("model artifact package version mismatch")
    if manifest.get("upstream_revision") != UPSTREAM_REVISION:
        raise ValueError("model artifact upstream revision mismatch")
    records = manifest.get("files", [])
    listed = {record["path"] for record in records}
    actual = set()
    for path in model_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError("model artifact contains a symbolic link")
        if path.is_file() and path.name != MANIFEST_NAME:
            actual.add(path.relative_to(model_dir).as_posix())
    if listed != actual:
        raise ValueError("model artifact inventory mismatch")
    for record in records:
        path = resolve_under(model_dir, record["path"])
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"artifact file is missing or unsafe: {record['path']}")
        if path.stat().st_size != record["bytes"]:
            raise ValueError(f"artifact size mismatch: {record['path']}")
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"artifact hash mismatch: {record['path']}")
    manifest["manifest_sha256"] = actual_manifest_sha
    return manifest
