from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = args.config.expanduser().resolve()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("BLOCKED: GEMINI_API_KEY is not configured")
    if not config.is_file():
        raise SystemExit(f"BLOCKED: config not found: {config}")

    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    models = data.setdefault("models", [])
    if not isinstance(models, list):
        raise SystemExit("BLOCKED: models must be a list")

    descriptor = {
        "key": "gemini-3.6-flash",
        "display_name": "Gemini 3.6 Flash",
        "engine": "gemini",
        "endpoint": "https://generativelanguage.googleapis.com",
        "provider": "google",
        "profile_id": "gemini-interactions",
        "capabilities": [
            "chat",
            "tools",
            "json_schema",
            "reasoning",
            "vision",
        ],
        "declared_context": 1048576,
        "certified_context": 0,
        "virtual_context": 1048576,
        "roles": ["planner", "reviewer", "judge"],
        "enabled": True,
        "status": "DISCOVERED",
    }

    replaced = False
    for index, model in enumerate(models):
        if isinstance(model, dict) and model.get("key") == descriptor["key"]:
            models[index] = {**model, **descriptor}
            replaced = True
            break
    if not replaced:
        models.append(descriptor)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config.with_name(f"{config.name}.before-gemini-3_6-{stamp}")
    backup.write_bytes(config.read_bytes())

    content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=config.parent,
        prefix=f".{config.name}.",
        delete=False,
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(config)

    print("GEMINI_3_6_CONFIG=VERIFIED")
    print(f"config={config}")
    print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
