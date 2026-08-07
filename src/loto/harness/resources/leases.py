from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO


class ResourceLeaseTimeout(TimeoutError):
    pass


class FileResourceLeaseManager:
    """Cross-process advisory leases for model loading and exclusive writers on Linux."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(resource: str) -> str:
        normalized = "".join(char if char.isalnum() or char in "-_." else "_" for char in resource)
        if not normalized or normalized in {".", ".."}:
            raise ValueError("invalid resource name")
        return normalized[:200]

    @contextmanager
    def acquire(
        self,
        resource: str,
        *,
        timeout_seconds: float = 300,
        poll_seconds: float = 0.1,
    ) -> Iterator[Path]:
        if timeout_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("lease timeout and poll interval must be positive")
        path = self.root / f"{self._safe_name(resource)}.lock"
        handle: IO[str] = path.open("a+", encoding="utf-8")
        deadline = time.monotonic() + timeout_seconds
        acquired = False
        try:
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    time.sleep(poll_seconds)
            if not acquired:
                raise ResourceLeaseTimeout(f"resource lease timed out: {resource}")
            handle.seek(0)
            handle.truncate()
            json.dump(
                {
                    "resource": resource,
                    "pid": os.getpid(),
                    "acquired_at": datetime.now(UTC).isoformat(),
                },
                handle,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            yield path
        finally:
            if acquired:
                handle.seek(0)
                handle.truncate()
                handle.write(
                    json.dumps(
                        {
                            "resource": resource,
                            "pid": os.getpid(),
                            "released_at": datetime.now(UTC).isoformat(),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                handle.flush()
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
