from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.orchestration.pipeline_downstream_preflight_errors import (
    DownstreamCommitConflict,
    DownstreamCommitError,
    DownstreamCommitPreflightError,
    DownstreamCommitRetryable,
)
from loto.orchestration.pipeline_downstream_preflight_io import (
    IMMUTABLE_ARTIFACTS,
    REQUIRED_DEFERRED_OPERATIONS,
    JsonValidator,
    SealVerifier,
    StagedCommitPlan,
    absolute_path,
    file_sha256,
    load_json,
    reject_symlink_components,
    require_regular_file,
)
from loto.orchestration.pipeline_downstream_preflight_validation import (
    default_ledger_validator,
    default_seal_verifier,
    float_metrics,
)
from loto.orchestration.pipeline_downstream_types import (
    ArtifactSnapshotItem,
    PreparedDownstreamCommit,
    canonical_json_bytes,
    sha256_value,
)


def prepare_downstream_commit(
    output_dir: str | Path,
    *,
    secret: bytes,
    ledger_validator: JsonValidator | None = None,
    seal_verifier: SealVerifier | None = None,
) -> PreparedDownstreamCommit:
    if not isinstance(secret, bytes) or len(secret) < 16:
        raise DownstreamCommitPreflightError("secret must contain at least 16 bytes")
    root = absolute_path(Path(output_dir))
    reject_symlink_components(root, label="staged output")
    if not root.is_dir():
        raise DownstreamCommitPreflightError(f"staged output is not a directory: {root}")

    paths = {name: root / name for name in IMMUTABLE_ARTIFACTS}
    for name, path in paths.items():
        require_regular_file(path, label=name)

    plan_payload = load_json(paths["downstream_commit_plan.json"])
    try:
        plan = StagedCommitPlan.model_validate(plan_payload)
    except Exception as exc:
        raise DownstreamCommitPreflightError(
            f"invalid downstream commit plan: {type(exc).__name__}"
        ) from exc
    if plan.status != "READY_FOR_DOWNSTREAM_COMMIT" or plan.executed:
        raise DownstreamCommitPreflightError(
            "downstream commit plan is not an unexecuted READY plan"
        )
    missing_operations = REQUIRED_DEFERRED_OPERATIONS.difference(plan.deferred_operations)
    if missing_operations:
        raise DownstreamCommitPreflightError(
            "downstream commit plan is missing operations: " + ",".join(sorted(missing_operations))
        )

    ledger_payload = load_json(paths["pipeline_data_access_ledger.json"])
    saved_validation = load_json(paths["pipeline_data_access_validation.json"])
    pipeline_report = load_json(paths["pipeline_data_access_report.json"])
    validated = (ledger_validator or default_ledger_validator)(
        ledger_payload,
        saved_validation,
    )
    if (
        validated.get("run_id") != plan.run_id
        or validated.get("ledger_sha256") != plan.ledger_sha256
    ):
        raise DownstreamCommitPreflightError(
            "plan run/hash does not match freshly validated ledger"
        )
    if saved_validation.get("status") != "PASS":
        raise DownstreamCommitPreflightError(
            "saved Data Access Ledger validation status is not PASS"
        )
    if saved_validation.get("run_id") != plan.run_id:
        raise DownstreamCommitPreflightError("saved validation run_id does not match plan")
    if saved_validation.get("ledger_sha256") != plan.ledger_sha256:
        raise DownstreamCommitPreflightError("saved validation ledger hash does not match plan")
    if int(saved_validation.get("error_count", -1)) != 0:
        raise DownstreamCommitPreflightError("saved validation contains errors")
    if (
        pipeline_report.get("status") != "PASS"
        or pipeline_report.get("complete") is not True
        or pipeline_report.get("downstream_commit_executed") is not False
        or pipeline_report.get("coverage_gaps") not in ([], None)
    ):
        raise DownstreamCommitPreflightError("pipeline report is not a complete pre-commit PASS")
    if pipeline_report.get("run_id") != plan.run_id:
        raise DownstreamCommitPreflightError("pipeline report run_id does not match plan")
    if pipeline_report.get("ledger_sha256") != plan.ledger_sha256:
        raise DownstreamCommitPreflightError("pipeline report ledger hash does not match plan")

    forecast = load_json(paths["forecast.json"])
    sealed = load_json(paths["forecast.sealed.json"])
    if not (seal_verifier or default_seal_verifier)(sealed, secret):
        raise DownstreamCommitPreflightError("forecast seal verification failed")
    if canonical_json_bytes(sealed.get("payload")) != canonical_json_bytes(forecast):
        raise DownstreamCommitPreflightError("sealed forecast payload differs from forecast.json")

    metadata = forecast.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("run_id") != plan.run_id:
        raise DownstreamCommitPreflightError("forecast metadata run_id does not match plan")
    required_forecast_fields = (
        "forecast_id",
        "draw_id",
        "model_id",
        "data_version",
        "feature_set_id",
    )
    missing_identity = any(
        not isinstance(forecast.get(name), str) or not forecast[name]
        for name in required_forecast_fields
    )
    if missing_identity:
        raise DownstreamCommitPreflightError("forecast identity fields are missing")

    evaluation = load_json(paths["evaluation.json"])
    champion = evaluation.get("champion")
    if champion not in {"uniform", "frequency"}:
        raise DownstreamCommitPreflightError(f"unsupported staged champion: {champion!r}")
    metrics = float_metrics(evaluation, champion)

    artifacts = [
        ArtifactSnapshotItem(
            relative_path=name,
            sha256=file_sha256(path),
            size_bytes=path.stat().st_size,
        )
        for name, path in paths.items()
    ]
    snapshot_payload = [
        item.model_dump(mode="json")
        for item in sorted(artifacts, key=lambda item: item.relative_path)
    ]
    snapshot_sha256 = sha256_value(snapshot_payload)
    commit_id = sha256_value(
        {
            "schema_version": "1.0.0",
            "run_id": plan.run_id,
            "ledger_sha256": plan.ledger_sha256,
            "forecast_id": forecast["forecast_id"],
            "snapshot_sha256": snapshot_sha256,
        }
    )
    return PreparedDownstreamCommit(
        output_dir=str(root),
        run_id=plan.run_id,
        commit_id=commit_id,
        ledger_sha256=plan.ledger_sha256,
        snapshot_sha256=snapshot_sha256,
        forecast_id=forecast["forecast_id"],
        draw_id=forecast["draw_id"],
        model_id=forecast["model_id"],
        data_version=forecast["data_version"],
        feature_set_id=forecast["feature_set_id"],
        release_id=f"release-{plan.run_id}",
        champion=champion,
        artifacts=artifacts,
        forecast=forecast,
        sealed_forecast=sealed,
        evaluation=evaluation,
        metrics=metrics,
    )


def verify_prepared_snapshot(prepared: PreparedDownstreamCommit) -> None:
    root = prepared.root
    observed: list[dict[str, Any]] = []
    for item in prepared.artifacts:
        path = root / item.relative_path
        require_regular_file(path, label=item.relative_path)
        digest = file_sha256(path)
        size = path.stat().st_size
        if digest != item.sha256 or size != item.size_bytes:
            raise DownstreamCommitConflict(
                f"staged artifact changed after preparation: {item.relative_path}"
            )
        observed.append(
            {
                "relative_path": item.relative_path,
                "sha256": digest,
                "size_bytes": size,
            }
        )
    observed_hash = sha256_value(sorted(observed, key=lambda value: value["relative_path"]))
    if observed_hash != prepared.snapshot_sha256:
        raise DownstreamCommitConflict("staged artifact snapshot hash changed")


__all__ = [
    "DownstreamCommitConflict",
    "DownstreamCommitError",
    "DownstreamCommitPreflightError",
    "DownstreamCommitRetryable",
    "IMMUTABLE_ARTIFACTS",
    "prepare_downstream_commit",
    "verify_prepared_snapshot",
]
