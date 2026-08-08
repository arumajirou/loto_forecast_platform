from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loto.orchestration.pipeline_downstream_effects_common import (
    atomic_write_json as _atomic_write_json,
    file_uri_path as _file_uri_path,
    json_equal as _json_equal,
    reject_symlink_components as _reject_symlink_components,
)
from loto.orchestration.pipeline_downstream_preflight import (
    DownstreamCommitConflict,
    DownstreamCommitRetryable,
)
from loto.orchestration.pipeline_downstream_types import PreparedDownstreamCommit


class StorageEffectsMixin:
    def ensure_release(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]:
        from loto.registry.release import (
            create_release_bundle,
            verify_release_bundle,
        )

        _reject_symlink_components(prepared.root, label="staged output")
        output = prepared.root / "release_bundle.json"
        paths = [prepared.root / item.relative_path for item in prepared.artifacts]
        if output.exists():
            if output.is_symlink() or not output.is_file():
                raise DownstreamCommitConflict("release_bundle.json is not a regular file")
            try:
                bundle = json.loads(output.read_text(encoding="utf-8"))
            except Exception as exc:
                raise DownstreamCommitConflict("existing release bundle is invalid JSON") from exc
            if bundle.get("release_id") != prepared.release_id:
                raise DownstreamCommitConflict("existing release bundle has another release_id")
            expected = {
                str(path.resolve()): (
                    next(
                        item.sha256
                        for item in prepared.artifacts
                        if item.relative_path == path.name
                    )
                )
                for path in paths
            }
            observed = {
                str(item["path"]): str(item["sha256"]) for item in bundle.get("artifacts", [])
            }
            if observed != expected:
                raise DownstreamCommitConflict("existing release bundle artifact set conflicts")
            if not verify_release_bundle(bundle):
                raise DownstreamCommitConflict("existing release bundle verification failed")
        else:
            bundle = create_release_bundle(
                prepared.release_id,
                paths,
                output,
            )
            if not verify_release_bundle(bundle):
                raise DownstreamCommitConflict("new release bundle verification failed")
        return {
            "release_id": prepared.release_id,
            "bundle_sha256": str(bundle["bundle_sha256"]),
            "path": str(output),
        }

    def ensure_artifact_store(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]:
        from loto.registry.artifacts import ArtifactStore

        _reject_symlink_components(
            self.config.artifact_store_root,
            label="artifact store",
        )
        store = ArtifactStore(self.config.artifact_store_root)
        source_paths = [prepared.root / item.relative_path for item in prepared.artifacts]
        source_paths.append(prepared.root / "release_bundle.json")
        index = {
            path.name: store.put_file(path, namespace=prepared.run_id) for path in source_paths
        }
        for source in source_paths:
            entry = index[source.name]
            stored = _file_uri_path(str(entry["uri"]))
            if not stored.is_file():
                raise DownstreamCommitRetryable(f"artifact store object is missing: {source.name}")
            if store.sha256(stored) != str(entry["sha256"]):
                raise DownstreamCommitConflict(
                    f"artifact store object hash mismatch: {source.name}"
                )
        output = prepared.root / "artifact_index.json"
        if output.exists():
            if output.is_symlink() or not output.is_file():
                raise DownstreamCommitConflict("artifact_index.json is not a regular file")
            current = json.loads(output.read_text(encoding="utf-8"))
            if not _json_equal(current, index):
                raise DownstreamCommitConflict(
                    "existing artifact index conflicts with current artifacts"
                )
        else:
            _atomic_write_json(output, index)
        return {
            "artifact_count": len(index),
            "artifact_index": str(output),
            "release_bundle_uri": index["release_bundle.json"]["uri"],
        }

    def ensure_mlflow(
        self,
        prepared: PreparedDownstreamCommit,
    ) -> dict[str, Any]:
        try:
            import mlflow
        except ImportError as exc:
            raise DownstreamCommitRetryable("mlflow_not_installed") from exc

        try:
            mlflow.set_tracking_uri(self.config.mlflow_tracking_uri)
            experiment = mlflow.get_experiment_by_name(self.config.mlflow_experiment_name)
            experiment_id = (
                mlflow.create_experiment(self.config.mlflow_experiment_name)
                if experiment is None
                else experiment.experiment_id
            )
            filter_string = f"tags.loto_commit_id = '{prepared.commit_id}'"
            existing = mlflow.search_runs(
                experiment_ids=[experiment_id],
                filter_string=filter_string,
                max_results=2,
                output_format="list",
            )
            if len(existing) > 1:
                raise DownstreamCommitConflict("multiple MLflow runs use the same commit_id")
            if existing:
                run = existing[0]
                tags = dict(getattr(run.data, "tags", {}))
                if (
                    tags.get("loto_run_id") != prepared.run_id
                    or tags.get("loto_ledger_sha256") != prepared.ledger_sha256
                ):
                    raise DownstreamCommitConflict(
                        "existing MLflow run conflicts with commit evidence"
                    )
                return {
                    "enabled": True,
                    "existing": True,
                    "run_id": run.info.run_id,
                    "tracking_uri": self.config.mlflow_tracking_uri,
                    "experiment_name": self.config.mlflow_experiment_name,
                }

            artifacts = [prepared.root / item.relative_path for item in prepared.artifacts]
            artifacts.extend(
                [
                    prepared.root / "release_bundle.json",
                    prepared.root / "artifact_index.json",
                ]
            )
            params = {
                "commit_id": prepared.commit_id,
                "ledger_sha256": prepared.ledger_sha256,
                "data_version": prepared.data_version,
                "feature_set_id": prepared.feature_set_id,
                "champion": prepared.champion,
                "release_id": prepared.release_id,
            }
            with mlflow.start_run(
                experiment_id=experiment_id,
                run_name=f"pipeline-{prepared.run_id}",
            ) as run:
                mlflow.set_tag("loto_commit_id", prepared.commit_id)
                mlflow.set_tag("loto_run_id", prepared.run_id)
                mlflow.set_tag("loto_ledger_sha256", prepared.ledger_sha256)
                mlflow.log_params(params)
                mlflow.log_metrics(prepared.metrics)
                for artifact in artifacts:
                    mlflow.log_artifact(str(artifact))
                return {
                    "enabled": True,
                    "existing": False,
                    "run_id": run.info.run_id,
                    "tracking_uri": self.config.mlflow_tracking_uri,
                    "experiment_name": self.config.mlflow_experiment_name,
                }
        except DownstreamCommitConflict:
            raise
        except Exception as exc:
            raise DownstreamCommitRetryable(
                f"mlflow_error:{type(exc).__name__}:{str(exc)[:500]}"
            ) from exc
