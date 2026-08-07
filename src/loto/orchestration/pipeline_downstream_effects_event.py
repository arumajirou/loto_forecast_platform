from __future__ import annotations

import json
from typing import Any

from loto.orchestration.pipeline_downstream_effects_common import (
    reject_symlink_components as _reject_symlink_components,
)
from loto.orchestration.pipeline_downstream_preflight import DownstreamCommitConflict
from loto.orchestration.pipeline_downstream_types import PreparedDownstreamCommit

class EventEffectsMixin:
    def ensure_event(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]:
        from loto.events.publisher import EventPublisher

        path = self.config.events_path
        _reject_symlink_components(path, label="events path")
        matches = []
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise DownstreamCommitConflict(
                    "events path is not a regular file"
                )
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DownstreamCommitConflict(
                        "events file contains invalid JSON"
                    ) from exc
                data = event.get("data")
                if (
                    event.get("type") == "pipeline.downstream.committed"
                    and isinstance(data, dict)
                    and data.get("commit_id") == prepared.commit_id
                ):
                    matches.append(event)
        if len(matches) > 1:
            raise DownstreamCommitConflict(
                "duplicate downstream commit events exist"
            )
        if matches:
            event = matches[0]
        else:
            event = EventPublisher(path).publish(
                "pipeline.downstream.committed",
                {
                    "commit_id": prepared.commit_id,
                    "run_id": prepared.run_id,
                    "ledger_sha256": prepared.ledger_sha256,
                    "forecast_id": prepared.forecast_id,
                    "release_id": prepared.release_id,
                    "status": "DOWNSTREAM_COMMITTED",
                },
            )
        return {
            "events_path": str(path),
            "event_id": event["event_id"],
        }
