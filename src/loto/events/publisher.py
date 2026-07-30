from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path


class EventPublisher:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, event_type: str, data: dict, *, schema_version: str = "1.0.0") -> dict:
        event = {
            "event_id": f"evt-{uuid.uuid4().hex[:16]}",
            "type": event_type,
            "schema_version": schema_version,
            "occurred_at": datetime.now(UTC).isoformat(),
            "data": data,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            fh.flush()
        return event
