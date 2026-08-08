from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from loto.orchestration.pipeline_downstream_effects_common import (
    json_equal as _json_equal,
    reject_symlink_components as _reject_symlink_components,
)
from loto.orchestration.pipeline_downstream_preflight import (
    DownstreamCommitConflict,
    DownstreamCommitRetryable,
)
from loto.orchestration.pipeline_downstream_types import PreparedDownstreamCommit


class LegacyRegistryEffectsMixin:
    def ensure_legacy_registry(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]:
        from loto.registry.sqlite import Registry

        _reject_symlink_components(
            self.config.registry_path,
            label="legacy registry",
        )
        registry = Registry(self.config.registry_path)
        with sqlite3.connect(registry.path) as connection:
            row = connection.execute(
                "SELECT run_id,sealed_json,verified FROM forecasts WHERE forecast_id=?",
                (prepared.forecast_id,),
            ).fetchone()
        if row is None:
            try:
                registry.record_forecast(
                    prepared.forecast_id,
                    prepared.run_id,
                    prepared.sealed_forecast,
                    True,
                )
            except sqlite3.IntegrityError:
                pass
            with sqlite3.connect(registry.path) as connection:
                row = connection.execute(
                    "SELECT run_id,sealed_json,verified FROM forecasts WHERE forecast_id=?",
                    (prepared.forecast_id,),
                ).fetchone()
        if row is None:
            raise DownstreamCommitRetryable("legacy registry forecast row was not persisted")
        if (
            str(row[0]) != prepared.run_id
            or int(row[2]) != 1
            or not _json_equal(
                json.loads(str(row[1])),
                prepared.sealed_forecast,
            )
        ):
            raise DownstreamCommitConflict(
                "legacy registry forecast conflicts with prepared forecast"
            )

        stage_matches = []
        for item in registry.list_stage_events(prepared.run_id):
            payload = item.get("payload")
            if (
                item.get("stage") == "DOWNSTREAM_COMMIT"
                and isinstance(payload, dict)
                and payload.get("commit_id") == prepared.commit_id
            ):
                stage_matches.append(item)
        if len(stage_matches) > 1:
            raise DownstreamCommitConflict("duplicate downstream commit stage events exist")
        if stage_matches:
            if stage_matches[0].get("status") != "SUCCEEDED":
                raise DownstreamCommitConflict("existing downstream commit stage is not SUCCEEDED")
        else:
            registry.record_stage(
                prepared.run_id,
                "DOWNSTREAM_COMMIT",
                "SUCCEEDED",
                {
                    "commit_id": prepared.commit_id,
                    "ledger_sha256": prepared.ledger_sha256,
                    "release_id": prepared.release_id,
                },
            )
        return {
            "registry_path": str(registry.path),
            "stage_event": "SUCCEEDED",
            "forecast_id": prepared.forecast_id,
        }
