from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable
from pathlib import Path

from .errors import UnsafeOperation

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|cookie)"
    r"\s*[:=]\s*([^\s,;]+)"
)


def redact_text(value: str) -> str:
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def environment_name_inventory(env: dict[str, str] | None = None) -> list[str]:
    values = env if env is not None else dict(os.environ)
    return sorted(values)


def ensure_allowed_path(path: str | Path, allowed_roots: Iterable[str | Path]) -> Path:
    candidate = Path(path).expanduser().resolve()
    roots = [Path(root).expanduser().resolve() for root in allowed_roots]
    if not roots:
        raise UnsafeOperation("no allowed roots configured")
    if not any(candidate == root or root in candidate.parents for root in roots):
        raise UnsafeOperation(f"path outside allowlist: {candidate}")
    return candidate


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(content: str) -> str:
    return sha256_bytes(content.encode("utf-8"))
