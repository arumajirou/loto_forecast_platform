from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loto_ops.config import AppSettings


def setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("loto_ops")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)

    # Use RotatingFileHandler for log rotation (100KB max, 3 backups)
    from logging.handlers import RotatingFileHandler

    fh = RotatingFileHandler(
        log_path,
        encoding="utf-8",
        maxBytes=1024 * 100,  # 100KB
        backupCount=3,
    )
    fh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


def append_event(events_path: Path, event: dict[str, Any]) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    item = {"ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z", **event}
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_reproduce_metadata(run_dir: Path, settings: AppSettings) -> None:
    """Write reproduce metadata JSON for pipeline reproducibility."""
    # Collect environment variables starting with LOTO_ or DB_
    env_vars: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith(("LOTO_", "DB_")):
            env_vars[key] = value

    # Build safe config summary (exclude secrets like db.password)
    config_summary: dict[str, Any] = {}
    if hasattr(settings, "raw") and settings.raw:
        for key, value in settings.raw.items():
            if isinstance(value, dict):
                # Filter out sensitive keys in nested dicts
                config_summary[key] = {
                    k: ("***REDACTED***" if k == "password" else v) for k, v in value.items()
                }
            elif key != "password":
                config_summary[key] = value

    metadata: dict[str, Any] = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python_version": sys.version,
        "platform": sys.platform,
        "environment_variables": env_vars,
        "config_summary": config_summary,
    }

    metadata_path = run_dir / "reproduce.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
