from __future__ import annotations

from pathlib import Path

import yaml


def load_quality_rules(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
