"""Self-verifying integrity manifest.

Constitution principle VII. The v2.1.0 artifact shipped two disagreeing checksum manifests
(``verification/SHA256SUMS``, stale, 14 of 82 mismatched, and
``RELEASE_MANIFEST_V2_1.json``, current). A third party running ``sha256sum -c`` saw 14
FAILED lines and had no way to tell staleness from tampering.

This module defines exactly one authoritative manifest, ``INTEGRITY.json``, and provides
generate / verify / prune operations plus a CLI. Verification distinguishes three outcomes
that a raw ``sha256sum -c`` conflates:

``MODIFIED``  file present, digest differs -> real integrity failure
``MISSING``   listed file absent           -> incomplete artifact
``UNTRACKED`` file present, not listed     -> manifest is stale, not the file

A stale manifest is a release-blocking defect, so ``verify`` fails on ``UNTRACKED`` too
unless the path matches an explicit exclusion rule.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from loto.version import __version__

__all__ = [
    "MANIFEST_NAME",
    "DEFAULT_EXCLUDES",
    "IntegrityReport",
    "iter_tracked_files",
    "file_digest",
    "generate_manifest",
    "verify_manifest",
    "main",
]

MANIFEST_NAME = "INTEGRITY.json"
MANIFEST_SCHEMA = "3.0.0"

#: Glob-ish prefixes and suffixes never tracked. Generated artefacts and caches only.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "htmlcov/",
    "node_modules/",
    ".coverage",
    "coverage.json",
    "coverage.xml",
    ".DS_Store",
    MANIFEST_NAME,
    "runs/",
    "evidence/",
    ".cache/",
    "dist/",
    "build/",
)

_BINARY_EXCLUDE_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo", ".so", ".egg-info")


def _is_excluded(rel: str, excludes: tuple[str, ...]) -> bool:
    normalised = rel.replace(os.sep, "/")
    for pattern in excludes:
        if pattern.endswith("/"):
            if normalised.startswith(pattern) or f"/{pattern}" in f"/{normalised}":
                return True
        elif normalised == pattern or normalised.endswith(f"/{pattern}"):
            return True
    return normalised.endswith(_BINARY_EXCLUDE_SUFFIXES)


def iter_tracked_files(root: Path, excludes: tuple[str, ...] = DEFAULT_EXCLUDES) -> list[str]:
    """Sorted list of POSIX-style relative paths eligible for tracking."""
    root = Path(root).resolve()
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if _is_excluded(rel, excludes):
            continue
        out.append(rel)
    return sorted(out)


def file_digest(path: Path, *, chunk: int = 1 << 20) -> tuple[str, int]:
    """Streaming SHA-256 so a large file does not have to fit in memory."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            size += len(block)
            digest.update(block)
    return digest.hexdigest(), size


@dataclass
class IntegrityReport:
    """Outcome of a verification pass."""

    root: str
    manifest_path: str
    manifest_schema: str
    release: str
    generated_at: str
    n_tracked: int
    n_verified: int = 0
    modified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    manifest_digest_expected: str = ""
    manifest_digest_actual: str = ""

    @property
    def ok(self) -> bool:
        return not (self.modified or self.missing or self.untracked)

    @property
    def status(self) -> str:
        if self.ok:
            return "VERIFIED"
        if self.modified:
            return "MODIFIED"
        if self.missing:
            return "INCOMPLETE"
        return "STALE_MANIFEST"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ok": self.ok,
            "root": self.root,
            "manifest_path": self.manifest_path,
            "manifest_schema": self.manifest_schema,
            "release": self.release,
            "generated_at": self.generated_at,
            "n_tracked": self.n_tracked,
            "n_verified": self.n_verified,
            "modified": self.modified,
            "missing": self.missing,
            "untracked": self.untracked,
            "self_digest_expected": self.manifest_digest_expected,
            "self_digest_actual": self.manifest_digest_actual,
        }

    def render(self) -> str:
        lines = [
            f"status            : {self.status}",
            f"release           : {self.release}",
            f"generated_at      : {self.generated_at}",
            f"tracked / verified: {self.n_tracked} / {self.n_verified}",
        ]
        for label, items in (
            ("MODIFIED", self.modified),
            ("MISSING", self.missing),
            ("UNTRACKED", self.untracked),
        ):
            if items:
                lines.append(f"{label:<18}: {len(items)}")
                lines.extend(f"    - {p}" for p in items[:25])
                if len(items) > 25:
                    lines.append(f"    … and {len(items) - 25} more")
        return "\n".join(lines)


def generate_manifest(
    root: str | Path,
    *,
    release: str | None = None,
    excludes: tuple[str, ...] = DEFAULT_EXCLUDES,
    write: bool = True,
) -> dict[str, object]:
    """Build (and optionally write) the single authoritative manifest."""
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"{root_path} is not a directory")
    resolved_release = __version__ if release is None else release
    files = iter_tracked_files(root_path, excludes)
    entries: dict[str, dict[str, object]] = {}
    total = 0
    for rel in files:
        digest, size = file_digest(root_path / rel)
        entries[rel] = {"sha256": digest, "bytes": size}
        total += size
    payload: dict[str, object] = {
        "manifest_schema": MANIFEST_SCHEMA,
        "release": resolved_release,
        "generated_at": datetime.now(UTC).isoformat(),
        "root_name": root_path.name,
        "excludes": list(excludes),
        "n_files": len(entries),
        "total_bytes": total,
        "files": entries,
    }
    # self-digest covers everything except the self-digest field itself
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["self_digest"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    if write:
        target = root_path / MANIFEST_NAME
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def verify_manifest(
    root: str | Path, *, manifest: str | Path | None = None, strict_untracked: bool = True
) -> IntegrityReport:
    """Verify a tree against its manifest.

    ``strict_untracked=True`` (the default) treats an untracked file as a failure, which is
    what makes manifest staleness detectable instead of invisible.
    """
    root_path = Path(root).resolve()
    manifest_path = Path(manifest) if manifest else root_path / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"integrity manifest not found: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    expected_self = str(payload.get("self_digest", ""))
    recomputed = {k: v for k, v in payload.items() if k != "self_digest"}
    blob = json.dumps(recomputed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    actual_self = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    files: dict[str, dict[str, object]] = payload.get("files", {})  # type: ignore[assignment]
    excludes = tuple(payload.get("excludes", DEFAULT_EXCLUDES))  # type: ignore[arg-type]

    report = IntegrityReport(
        root=str(root_path),
        manifest_path=str(manifest_path),
        manifest_schema=str(payload.get("manifest_schema", "")),
        release=str(payload.get("release", "")),
        generated_at=str(payload.get("generated_at", "")),
        n_tracked=len(files),
        manifest_digest_expected=expected_self,
        manifest_digest_actual=actual_self,
    )
    if expected_self and expected_self != actual_self:
        report.modified.append(f"{MANIFEST_NAME} (self-digest mismatch)")

    for rel, meta in sorted(files.items()):
        target = root_path / rel
        if not target.is_file():
            report.missing.append(rel)
            continue
        digest, _ = file_digest(target)
        if digest != meta.get("sha256"):
            report.modified.append(rel)
        else:
            report.n_verified += 1

    if strict_untracked:
        present = set(iter_tracked_files(root_path, excludes))
        report.untracked = sorted(present - set(files))
    return report


def main(argv: list[str] | None = None) -> int:
    """``python -m loto.verify.integrity {generate,check} [root]``"""
    import argparse

    parser = argparse.ArgumentParser(prog="loto-integrity", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="write INTEGRITY.json")
    gen.add_argument("root", nargs="?", default=".")
    gen.add_argument("--release", default=__version__)
    chk = sub.add_parser("check", help="verify a tree against INTEGRITY.json")
    chk.add_argument("root", nargs="?", default=".")
    chk.add_argument("--manifest", default=None)
    chk.add_argument("--allow-untracked", action="store_true")
    chk.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "generate":
        payload = generate_manifest(args.root, release=args.release)
        print(
            f"wrote {MANIFEST_NAME}: {payload['n_files']} files, "
            f"{payload['total_bytes']} bytes, self_digest={payload['self_digest'][:16]}…"
        )
        return 0

    report = verify_manifest(
        args.root, manifest=args.manifest, strict_untracked=not args.allow_untracked
    )
    print(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) if args.json else report.render()
    )
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
