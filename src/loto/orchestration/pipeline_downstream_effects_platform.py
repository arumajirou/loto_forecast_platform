from __future__ import annotations

import json
from typing import Any

from loto.orchestration.pipeline_downstream_effects_common import (
    json_equal as _json_equal,
    platform_local_path as _platform_local_path,
    reject_symlink_components as _reject_symlink_components,
)
from loto.orchestration.pipeline_downstream_preflight import (
    DownstreamCommitConflict,
    DownstreamCommitRetryable,
)
from loto.orchestration.pipeline_downstream_types import PreparedDownstreamCommit


class PlatformRegistryEffectsMixin:
    @staticmethod
    def _platform_row(
        platform: Any,
        table: str,
        key: str,
        value: str,
    ) -> dict[str, Any] | None:
        placeholder = platform.db.placeholder
        with platform.db.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {table} WHERE {key}={placeholder}",
                (value,),
            )
            row = cursor.fetchone()
            description = cursor.description
        if row is None:
            return None
        if hasattr(row, "keys"):
            return dict(row)
        if description is None:
            raise DownstreamCommitConflict(f"cannot inspect PlatformRegistry {table} columns")
        names = [str(getattr(item, "name", item[0])) for item in description]
        return dict(zip(names, row, strict=True))

    def ensure_platform_registry(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]:
        from loto.registry.full import PlatformRegistry

        local_platform_path = _platform_local_path(self.config.platform_registry_url)
        if local_platform_path is not None:
            _reject_symlink_components(
                local_platform_path,
                label="platform registry",
            )
        artifact_index = json.loads(
            (prepared.root / "artifact_index.json").read_text(encoding="utf-8")
        )
        release_uri = artifact_index["release_bundle.json"]["uri"]
        platform = PlatformRegistry(self.config.platform_registry_url)
        run = self._platform_row(
            platform,
            "runs",
            "run_id",
            prepared.run_id,
        )
        if run is None:
            try:
                platform.create_run(
                    prepared.run_id,
                    config_hash=prepared.ledger_sha256,
                )
            except Exception:
                run = self._platform_row(
                    platform,
                    "runs",
                    "run_id",
                    prepared.run_id,
                )
                if run is None:
                    raise
        else:
            config_hash = str(run.get("config_hash") or "")
            if config_hash not in {"", prepared.ledger_sha256}:
                raise DownstreamCommitConflict("PlatformRegistry run config_hash conflicts")

        platform.update_run(
            prepared.run_id,
            status="COMMITTING",
            current_stage="DOWNSTREAM_COMMIT",
        )
        platform.record_task(
            prepared.run_id,
            "DOWNSTREAM_COMMIT",
            "RUNNING",
            input_hash=prepared.snapshot_sha256,
            output_uri=release_uri,
        )
        platform.register_forecast(
            prepared.forecast_id,
            prepared.run_id,
            prepared.draw_id,
            prepared.sealed_forecast,
            True,
            status="SEALED_CANDIDATE",
        )
        forecast = self._platform_row(
            platform,
            "forecasts",
            "forecast_id",
            prepared.forecast_id,
        )
        if forecast is None:
            raise DownstreamCommitRetryable("PlatformRegistry forecast was not persisted")
        if (
            str(forecast.get("run_id")) != prepared.run_id
            or str(forecast.get("draw_id")) != prepared.draw_id
            or int(forecast.get("verified", 0)) != 1
            or not _json_equal(
                json.loads(str(forecast.get("sealed_json"))),
                prepared.sealed_forecast,
            )
        ):
            raise DownstreamCommitConflict("PlatformRegistry forecast conflicts")

        model_metadata = {
            "run_id": prepared.run_id,
            "commit_id": prepared.commit_id,
            "ledger_sha256": prepared.ledger_sha256,
            "data_version": prepared.data_version,
            "feature_set_id": prepared.feature_set_id,
            "release_id": prepared.release_id,
        }
        platform.register_model(
            prepared.model_id,
            prepared.champion,
            release_uri,
            prepared.evaluation[prepared.champion],
            model_metadata,
            status="CANDIDATE",
        )
        model = self._platform_row(
            platform,
            "models",
            "model_id",
            prepared.model_id,
        )
        if model is None:
            raise DownstreamCommitRetryable("PlatformRegistry model was not persisted")
        if (
            str(model.get("artifact_uri")) != release_uri
            or str(model.get("status")) != "CANDIDATE"
            or not _json_equal(
                json.loads(str(model.get("metadata_json"))),
                model_metadata,
            )
        ):
            raise DownstreamCommitConflict(
                "PlatformRegistry model_id already refers to other evidence"
            )

        platform.record_task(
            prepared.run_id,
            "DOWNSTREAM_COMMIT",
            "SUCCEEDED",
            input_hash=prepared.snapshot_sha256,
            output_uri=release_uri,
        )
        platform.update_run(
            prepared.run_id,
            status="DOWNSTREAM_COMMITTED",
            current_stage="REGISTER",
            release_id=prepared.release_id,
        )
        audit_matches = []
        placeholder = platform.db.placeholder
        with platform.db.connect() as connection:
            rows = (
                connection.cursor()
                .execute(
                    "SELECT * FROM audit_log WHERE object_type="
                    f"{placeholder} AND object_id={placeholder}",
                    ("run", prepared.run_id),
                )
                .fetchall()
            )
        for row in rows:
            value = dict(row) if hasattr(row, "keys") else {}
            try:
                payload = json.loads(str(value.get("payload_json", "{}")))
            except json.JSONDecodeError:
                continue
            if (
                value.get("action") == "downstream_commit"
                and payload.get("commit_id") == prepared.commit_id
            ):
                audit_matches.append(value)
        if len(audit_matches) > 1:
            raise DownstreamCommitConflict("duplicate PlatformRegistry commit audits exist")
        if not audit_matches:
            platform.audit(
                "system",
                "downstream_commit",
                "run",
                prepared.run_id,
                "Data Access Ledger gated downstream commit",
                {
                    "commit_id": prepared.commit_id,
                    "ledger_sha256": prepared.ledger_sha256,
                    "release_id": prepared.release_id,
                },
            )
        return {
            "platform_registry_url": self.config.platform_registry_url,
            "run_status": "DOWNSTREAM_COMMITTED",
            "forecast_id": prepared.forecast_id,
            "model_id": prepared.model_id,
            "release_uri": release_uri,
        }
