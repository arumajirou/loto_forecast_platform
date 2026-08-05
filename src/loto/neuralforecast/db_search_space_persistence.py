"""Failure-durable search-space evidence for database AutoModel campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from loto.models.neuralforecast_search_space import (
    SearchSpaceProfile,
    profile_runtime_model_config,
    unavailable_search_space_profile,
)
from loto.models.neuralforecast_search_space_artifacts import (
    persist_search_space_artifacts,
    verify_search_space_artifacts,
)


class DatabaseSearchSpaceEvidence(BaseModel):
    """Serializable evidence embedded in model and campaign reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    phase: str
    profile: SearchSpaceProfile
    artifacts: dict[str, Any] = Field(default_factory=dict)


def unavailable_autohint_profile() -> SearchSpaceProfile:
    """Record honest pre-import evidence for AutoHINT's Ray-only runtime space."""

    return unavailable_search_space_profile(
        backend="ray",
        model_name="AutoHINT",
        reason=(
            "AutoHINT Ray domains are resolved only after optional neuralforecast "
            "and ray dependencies import successfully"
        ),
    )


def persist_database_search_space_evidence(
    model_directory: str | Path,
    profile: SearchSpaceProfile,
    *,
    phase: str,
    model_id: str,
    class_name: str,
    backend: str,
    search_seed: int,
    num_samples: int,
    planning_profile_sha256: str | None = None,
) -> dict[str, Any]:
    """Persist and verify the four-file contract in one model directory."""

    root = Path(model_directory)
    context: dict[str, Any] = {
        "phase": phase,
        "model_id": model_id,
        "class_name": class_name,
        "backend": backend,
        "search_seed": search_seed,
        "num_samples": num_samples,
    }
    if planning_profile_sha256 is not None:
        context["planning_profile_sha256"] = planning_profile_sha256
    artifacts = persist_search_space_artifacts(root, profile, context=context)
    verification = verify_search_space_artifacts(root)
    if verification["status"] != "PASS":
        raise RuntimeError(
            f"database search-space evidence verification failed: {verification}"
        )
    return DatabaseSearchSpaceEvidence(
        phase=phase,
        profile=profile,
        artifacts={**artifacts, "verification": verification},
    ).model_dump(mode="json")


def runtime_profile_for_model(
    model: Any,
    *,
    backend: str,
    model_name: str,
    fallback: SearchSpaceProfile,
) -> SearchSpaceProfile:
    """Prefer the adapter-attached runtime profile, then inspect model.config."""

    attached = getattr(model, "search_space_profile", None)
    if attached is not None:
        return SearchSpaceProfile.model_validate(attached)
    return profile_runtime_model_config(
        model,
        backend=backend,
        model_name=model_name,
        fallback=fallback,
    )


def summarize_database_search_space_reports(
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate profile verification independently from model success."""

    rows: list[dict[str, Any]] = []
    verified = 0
    failed = 0
    missing = 0
    for report in sorted(reports, key=lambda item: str(item.get("model_id"))):
        evidence = report.get("search_space_evidence")
        if not isinstance(evidence, dict):
            missing += 1
            rows.append(
                {
                    "model_id": report.get("model_id"),
                    "class_name": report.get("class_name"),
                    "status": "MISSING",
                }
            )
            continue
        artifacts = evidence.get("artifacts") or {}
        verification_status = artifacts.get("verification_status")
        if verification_status == "PASS":
            verified += 1
        else:
            failed += 1
        profile = evidence.get("profile") or {}
        rows.append(
            {
                "model_id": report.get("model_id"),
                "class_name": report.get("class_name"),
                "status": verification_status or "FAIL",
                "phase": evidence.get("phase"),
                "completeness": profile.get("completeness"),
                "profile_sha256": profile.get("profile_sha256"),
                "profile_file_sha256": artifacts.get("sha256"),
                "manifest_sha256": artifacts.get("manifest_sha256"),
            }
        )
    if reports and verified == len(reports):
        status = "PASS"
    elif verified:
        status = "PARTIAL"
    else:
        status = "FAIL"
    return {
        "schema_version": "1.0.0",
        "status": status,
        "model_count": len(reports),
        "verified_model_count": verified,
        "failed_verification_model_count": failed,
        "missing_evidence_model_count": missing,
        "profiles": rows,
    }
