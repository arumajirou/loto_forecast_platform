#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_MARKER = 'name = "loto-forecast-platform"'
HARNESS_BLOCK = """harness = [
  "fastapi>=0.115,<1", "httpx>=0.27,<1", "uvicorn>=0.34,<1",
  "mcp>=1.28,<2", "psycopg[binary]>=3.2,<4", "sqlalchemy>=2,<3",
  "alembic>=1,<2", "pgvector>=0.3,<1", "psutil>=6,<8",
  "structlog>=25,<26", "opentelemetry-sdk>=1.30,<2",
  "opentelemetry-exporter-otlp>=1.30,<2",
]
"""
SCRIPT_LINE = 'loto-harness = "loto.harness.cli:main"\n'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_pyproject_text(text: str) -> tuple[str, bool]:
    if PROJECT_MARKER not in text:
        raise RuntimeError("target pyproject is not loto-forecast-platform")
    changed = False
    if "\nharness = [\n" not in text:
        anchor = 'postgres = ["psycopg[binary]>=3.2", "sqlalchemy>=2.0"]\n'
        if anchor not in text:
            raise RuntimeError("pyproject optional-dependency anchor not found")
        text = text.replace(anchor, anchor + HARNESS_BLOCK, 1)
        changed = True
    if SCRIPT_LINE not in text:
        anchor = 'loto-integrity = "loto.verify.integrity:main"\n'
        if anchor not in text:
            raise RuntimeError("pyproject script anchor not found")
        text = text.replace(anchor, anchor + SCRIPT_LINE, 1)
        changed = True
    return text, changed


def overlay_files(overlay: Path) -> list[Path]:
    result: list[Path] = []
    for source in overlay.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(overlay)
        if "__pycache__" in relative.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        result.append(source)
    return sorted(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the audited loto harness overlay")
    parser.add_argument("target", help="loto_forecast_platform checkout")
    parser.add_argument("--overlay", default=str(Path(__file__).parent / "overlay"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    overlay = Path(args.overlay).expanduser().resolve()
    pyproject = target / "pyproject.toml"
    if not pyproject.is_file():
        raise SystemExit(f"target is not the repository root: {target}")
    if not (overlay / "src/loto/harness").is_dir():
        raise SystemExit(f"invalid overlay: {overlay}")

    original_pyproject = pyproject.read_text(encoding="utf-8")
    patched_pyproject, pyproject_changed = patch_pyproject_text(original_pyproject)
    sources = overlay_files(overlay)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = target / "artifacts" / "harness-overlay-backups" / timestamp
    manifest: list[dict[str, str | bool]] = []

    for source in sources:
        relative = source.relative_to(overlay)
        destination = target / relative
        source_sha = sha256_file(source)
        destination_sha = sha256_file(destination) if destination.is_file() else None
        action = (
            "unchanged"
            if source_sha == destination_sha
            else ("replace" if destination.exists() else "create")
        )
        manifest.append(
            {
                "path": relative.as_posix(),
                "action": action,
                "source_sha256": source_sha,
                "previous_sha256": destination_sha or "",
            }
        )
        if args.dry_run or action == "unchanged":
            continue
        if destination.exists():
            backup_file = backup / relative
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup_file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    if pyproject_changed and not args.dry_run:
        backup_pyproject = backup / "pyproject.toml"
        backup_pyproject.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pyproject, backup_pyproject)
        pyproject.write_text(patched_pyproject, encoding="utf-8")
    manifest.append(
        {
            "path": "pyproject.toml",
            "action": "patch" if pyproject_changed else "unchanged",
            "source_sha256": hashlib.sha256(patched_pyproject.encode()).hexdigest(),
            "previous_sha256": hashlib.sha256(original_pyproject.encode()).hexdigest(),
        }
    )

    claude_file = target / "CLAUDE.md"
    claude_import = "@CLAUDE.harness.md"
    claude_changed = False
    if claude_file.exists():
        claude_text = claude_file.read_text(encoding="utf-8")
        if claude_import not in claude_text.splitlines():
            claude_changed = True
            if not args.dry_run:
                backup_claude = backup / "CLAUDE.md"
                backup_claude.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(claude_file, backup_claude)
                separator = "" if not claude_text or claude_text.endswith("\n") else "\n"
                claude_file.write_text(
                    claude_text + separator + "\n" + claude_import + "\n",
                    encoding="utf-8",
                )
    else:
        claude_changed = True
        if not args.dry_run:
            claude_file.write_text(claude_import + "\n", encoding="utf-8")
    manifest.append(
        {
            "path": "CLAUDE.md",
            "action": "patch" if claude_changed else "unchanged",
            "source_sha256": "",
            "previous_sha256": "",
        }
    )

    if not args.dry_run:
        backup.mkdir(parents=True, exist_ok=True)
        (backup / "APPLY_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    changed_count = sum(item["action"] != "unchanged" for item in manifest)
    print("HARNESS_OVERLAY_APPLIED=DRY_RUN" if args.dry_run else "HARNESS_OVERLAY_APPLIED=VERIFIED")
    print(f"target={target}")
    print(f"backup={backup if not args.dry_run else 'NOT_CREATED'}")
    print(f"files={len(sources)}")
    print(f"changed={changed_count}")
    print(f"pyproject_changed={str(pyproject_changed).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
