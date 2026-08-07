from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from loto.merlion_campaign.bootstrap_resume import (
    PLAN_SCHEMA,
    PREFLIGHT_SCHEMA,
    _validate_hash_bound_payload,
)


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def validate_preflight_payload(
    preflight: Mapping[str, Any],
    *,
    require_attemptable: bool,
    expected_report_sha256: str | None = None,
) -> str:
    if preflight.get("schema_version") != PREFLIGHT_SCHEMA:
        raise ValueError("unsupported preflight schema")
    _validate_hash_bound_payload(preflight, hash_field="report_sha256")
    report_sha256 = str(preflight["report_sha256"])
    if expected_report_sha256 and report_sha256 != expected_report_sha256:
        raise ValueError("preflight report SHA-256 does not match expected lineage")
    if require_attemptable and preflight.get("can_attempt_bootstrap") is not True:
        raise ValueError("preflight does not allow bootstrap")
    return report_sha256


def validate_preflight_plan_lineage(
    preflight: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    require_attemptable: bool,
) -> dict[str, str]:
    preflight_sha256 = validate_preflight_payload(
        preflight,
        require_attemptable=require_attemptable,
    )
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("unsupported bootstrap plan schema")
    _validate_hash_bound_payload(plan, hash_field="plan_sha256")
    if plan.get("preflight_report_sha256") != preflight_sha256:
        raise ValueError("bootstrap plan preflight hash mismatch")
    return {
        "preflight_report_sha256": preflight_sha256,
        "plan_sha256": str(plan["plan_sha256"]),
    }


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("lineage file is missing or unsafe")
    return hashlib.sha256(path.read_bytes()).hexdigest()
