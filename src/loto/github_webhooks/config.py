from __future__ import annotations

from pathlib import Path

import yaml

from loto.github_webhooks.contracts import ReceiverPolicy


def load_receiver_policy(path: str | Path) -> ReceiverPolicy:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ReceiverPolicy.model_validate(raw)
