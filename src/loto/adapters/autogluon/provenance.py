from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

CONTEXT_FILENAME = "loto_provider_context_v2.json"
PLAN_FILENAME = "loto_execution_plan_v2.json"
MAPPING_FILENAME = "loto_timeline_mapping_v2.json"


class ArtifactContextError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SavedArtifactContext:
    context: dict[str, Any]
    execution_plan: dict[str, Any]
    timeline_mapping: dict[str, Any]
    artifacts: dict[str, str]


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _model_name_matches(alias: str, observed_name: str) -> bool:
    if observed_name == alias:
        return True
    return any(
        observed_name.startswith(f"{alias}{separator}")
        for separator in ("/", "_", "-")
    )


def model_identity_evidence(
    selected_model_ids: Iterable[str],
    observed_model_names: Iterable[str],
) -> dict[str, Any]:
    selected = [str(value) for value in selected_model_ids]
    observed = [str(value) for value in observed_model_names]
    missing = [
        alias
        for alias in selected
        if not any(_model_name_matches(alias, name) for name in observed)
    ]
    verified = bool(observed) and not missing
    return {
        "selected_model_ids": selected,
        "observed_model_names": observed,
        "missing_model_ids": missing,
        "verified": verified,
    }


def build_fit_context(
    *,
    run_id: str,
    request_payload: dict[str, Any],
    execution_plan: dict[str, Any],
    timeline_mapping: list[dict[str, Any]],
    source_order_sha256: str,
    timeline_mapping_sha256: str,
    geometry_sha256: str,
    library_version: str,
    model_names: list[str],
    model_best: str | None,
) -> dict[str, Any]:
    identity = model_identity_evidence(
        execution_plan.get("selected_model_ids", []),
        model_names,
    )
    if not identity["verified"]:
        raise ArtifactContextError(
            "MODEL_IDENTITY_NOT_VERIFIED",
            "trained model names do not prove the requested model identity",
        )
    return {
        "schema_version": 1,
        "provider_schema_version": 2,
        "provider_version": 2,
        "run_id": run_id,
        "request_sha256": canonical_sha256(request_payload),
        "execution_plan": execution_plan,
        "timeline_mapping": timeline_mapping,
        "source_order_sha256": source_order_sha256,
        "timeline_mapping_sha256": timeline_mapping_sha256,
        "geometry_sha256": geometry_sha256,
        "runtime_snapshot": {
            "library": "autogluon.timeseries",
            "library_version": library_version,
            "model_names": model_names,
            "model_best": model_best,
            "model_identity": identity,
        },
    }


def persist_fit_context(
    artifact_dir: Path,
    *,
    context: dict[str, Any],
) -> dict[str, str]:
    context_path = artifact_dir / CONTEXT_FILENAME
    plan_path = artifact_dir / PLAN_FILENAME
    mapping_path = artifact_dir / MAPPING_FILENAME
    write_json_atomic(context_path, context)
    write_json_atomic(plan_path, context["execution_plan"])
    write_json_atomic(
        mapping_path,
        {
            "mapping": context["timeline_mapping"],
            "source_order_sha256": context["source_order_sha256"],
            "timeline_mapping_sha256": context["timeline_mapping_sha256"],
            "geometry_sha256": context["geometry_sha256"],
        },
    )
    return {
        "artifact_dir": str(artifact_dir),
        "provider_context": str(context_path),
        "execution_plan": str(plan_path),
        "timeline_mapping": str(mapping_path),
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_MISSING",
            f"required artifact context file is missing: {path}",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_INVALID",
            f"cannot read artifact context file {path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_INVALID",
            f"artifact context file must contain a JSON object: {path}",
        )
    return value


def _validate_plan_hash(plan: dict[str, Any]) -> None:
    expected = plan.get("plan_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ArtifactContextError(
            "ARTIFACT_PLAN_HASH_INVALID",
            "saved execution plan has no valid plan_sha256",
        )
    payload = dict(plan)
    payload.pop("plan_sha256", None)
    actual = canonical_sha256(payload)
    if actual != expected:
        raise ArtifactContextError(
            "ARTIFACT_PLAN_HASH_MISMATCH",
            f"saved execution plan hash mismatch expected={expected} actual={actual}",
        )


def _predictor_contract(plan: dict[str, Any]) -> dict[str, Any]:
    predictor = plan.get("predictor_kwargs")
    if not isinstance(predictor, dict):
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_INVALID",
            "saved execution plan has no predictor_kwargs object",
        )
    keys = ("target", "prediction_length", "freq", "quantile_levels")
    return {key: predictor.get(key) for key in keys}


def validate_saved_artifact_context(
    artifact_dir: Path,
    *,
    current_execution_plan: dict[str, Any],
    current_geometry_sha256: str,
    expected_library_version: str,
) -> SavedArtifactContext:
    context_path = artifact_dir / CONTEXT_FILENAME
    plan_path = artifact_dir / PLAN_FILENAME
    mapping_path = artifact_dir / MAPPING_FILENAME
    context = _read_json_object(context_path)
    plan = _read_json_object(plan_path)
    mapping = _read_json_object(mapping_path)

    if context.get("schema_version") != 1:
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_VERSION_MISMATCH",
            "saved provider context schema_version must be 1",
        )
    if context.get("execution_plan") != plan:
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_PLAN_MISMATCH",
            "embedded and standalone execution plans differ",
        )
    _validate_plan_hash(plan)

    timeline = context.get("timeline_mapping")
    if not isinstance(timeline, list) or mapping.get("mapping") != timeline:
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_MAPPING_MISMATCH",
            "embedded and standalone timeline mappings differ",
        )
    actual_mapping_hash = canonical_sha256(timeline)
    if context.get("timeline_mapping_sha256") != actual_mapping_hash:
        raise ArtifactContextError(
            "ARTIFACT_MAPPING_HASH_MISMATCH",
            "saved timeline mapping hash does not match its payload",
        )
    source_payload = [
        {
            "source_index": row.get("source_index"),
            "source_order": row.get("source_order"),
            "source_timestamp": row.get("source_timestamp"),
        }
        for row in timeline
        if isinstance(row, dict)
    ]
    if len(source_payload) != len(timeline):
        raise ArtifactContextError(
            "ARTIFACT_CONTEXT_MAPPING_MISMATCH",
            "saved timeline mapping contains a non-object row",
        )
    if context.get("source_order_sha256") != canonical_sha256(source_payload):
        raise ArtifactContextError(
            "ARTIFACT_SOURCE_ORDER_HASH_MISMATCH",
            "saved source-order hash does not match its payload",
        )
    for key in ("source_order_sha256", "timeline_mapping_sha256", "geometry_sha256"):
        if mapping.get(key) != context.get(key):
            raise ArtifactContextError(
                "ARTIFACT_CONTEXT_MAPPING_MISMATCH",
                f"standalone mapping field {key!r} differs from provider context",
            )
    if context.get("geometry_sha256") != current_geometry_sha256:
        raise ArtifactContextError(
            "ARTIFACT_GEOMETRY_MISMATCH",
            "saved model geometry does not match the load request geometry",
        )

    if plan.get("execution_mode") != current_execution_plan.get("execution_mode"):
        raise ArtifactContextError(
            "ARTIFACT_EXECUTION_MODE_MISMATCH",
            "saved and requested execution modes differ",
        )
    saved_model_ids = list(plan.get("selected_model_ids") or [])
    current_model_ids = list(current_execution_plan.get("selected_model_ids") or [])
    if saved_model_ids != current_model_ids:
        raise ArtifactContextError(
            "ARTIFACT_MODEL_ID_MISMATCH",
            "saved and requested model identities differ",
        )
    if _predictor_contract(plan) != _predictor_contract(current_execution_plan):
        raise ArtifactContextError(
            "ARTIFACT_PREDICTOR_CONTRACT_MISMATCH",
            "saved and requested predictor contracts differ",
        )

    snapshot = context.get("runtime_snapshot")
    if not isinstance(snapshot, dict):
        raise ArtifactContextError(
            "ARTIFACT_RUNTIME_SNAPSHOT_MISSING",
            "saved context has no runtime_snapshot object",
        )
    if snapshot.get("library_version") != expected_library_version:
        raise ArtifactContextError(
            "ARTIFACT_LIBRARY_VERSION_MISMATCH",
            "saved model library version does not match the required runtime version",
        )
    identity = snapshot.get("model_identity")
    if not isinstance(identity, dict) or identity.get("verified") is not True:
        raise ArtifactContextError(
            "ARTIFACT_MODEL_IDENTITY_UNVERIFIED",
            "saved model identity is not verified",
        )
    if list(identity.get("selected_model_ids") or []) != saved_model_ids:
        raise ArtifactContextError(
            "ARTIFACT_MODEL_IDENTITY_MISMATCH",
            "saved model identity does not match the execution plan",
        )

    return SavedArtifactContext(
        context=context,
        execution_plan=plan,
        timeline_mapping=mapping,
        artifacts={
            "artifact_dir": str(artifact_dir),
            "provider_context": str(context_path),
            "execution_plan": str(plan_path),
            "timeline_mapping": str(mapping_path),
        },
    )
