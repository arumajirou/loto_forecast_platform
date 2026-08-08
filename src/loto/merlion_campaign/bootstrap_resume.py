from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PREFLIGHT_SCHEMA = "merlion-bootstrap-preflight-v1"
PLAN_SCHEMA = "merlion-bootstrap-resume-plan-v1"


def _canonical_sha256(payload: Mapping[str, Any], *, omit: str | None = None) -> str:
    filtered = {key: value for key, value in payload.items() if key != omit}
    encoded = json.dumps(filtered, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    temporary.replace(path)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _validate_hash_bound_payload(
    payload: Mapping[str, Any],
    *,
    hash_field: str,
) -> None:
    recorded = payload.get(hash_field)
    if not isinstance(recorded, str) or len(recorded) != 64:
        raise ValueError(f"{hash_field} is missing or invalid")
    expected = _canonical_sha256(payload, omit=hash_field)
    if recorded != expected:
        raise ValueError(f"{hash_field} mismatch")


def _network_map(preflight: Mapping[str, Any]) -> dict[str, bool]:
    rows = preflight.get("network_dns", [])
    if not isinstance(rows, list):
        return {}
    result: dict[str, bool] = {}
    for row in rows:
        if isinstance(row, Mapping) and isinstance(row.get("host"), str):
            result[str(row["host"])] = bool(row.get("reachable"))
    return result


def build_resume_plan(
    preflight: Mapping[str, Any],
    root: Path,
    *,
    run_id: str,
    managed_python_dir: Path | None = None,
) -> dict[str, Any]:
    if preflight.get("schema_version") != PREFLIGHT_SCHEMA:
        raise ValueError("unsupported preflight schema")
    _validate_hash_bound_payload(preflight, hash_field="report_sha256")

    root = root.resolve()
    managed = (
        managed_python_dir.resolve()
        if managed_python_dir is not None
        else root / "artifacts/merlion-managed-python/cpython-3.11"
    )
    uv = preflight.get("uv", {})
    python = preflight.get("python_311", {})
    if not isinstance(uv, Mapping) or not isinstance(python, Mapping):
        raise ValueError("preflight runtime sections are invalid")

    network = _network_map(preflight)
    github_ready = network.get("github.com", False)
    index_ready = network.get("pypi.org", False) and network.get("files.pythonhosted.org", False)
    blockers: list[str] = []
    steps: list[dict[str, Any]] = []
    environment: dict[str, str] = {}
    python_path = python.get("path") if python.get("found") else None

    if not uv.get("found"):
        blockers.append("UV_NOT_AVAILABLE")
    if not index_ready:
        blockers.append("PACKAGE_INDEX_DNS_UNAVAILABLE")

    if python_path:
        strategy = "USE_EXISTING_PYTHON_311"
        steps.append(
            {
                "name": "bootstrap",
                "command": ["bash", "scripts/bootstrap_merlion_core_env.sh"],
            }
        )
    elif github_ready and uv.get("found"):
        strategy = "INSTALL_UV_MANAGED_PYTHON_311"
        environment["UV_PYTHON_INSTALL_DIR"] = str(managed)
        steps.extend(
            [
                {
                    "name": "install_python",
                    "command": [
                        "uv",
                        "python",
                        "install",
                        "3.11",
                        "--install-dir",
                        str(managed),
                        "--no-bin",
                    ],
                },
                {
                    "name": "resolve_python",
                    "command": [
                        "uv",
                        "python",
                        "find",
                        "--managed-python",
                        "3.11",
                    ],
                },
                {
                    "name": "bootstrap",
                    "command": ["bash", "scripts/bootstrap_merlion_core_env.sh"],
                },
            ]
        )
    else:
        strategy = "BLOCKED_NO_PYTHON_311_SOURCE"
        blockers.append("PYTHON_311_UNAVAILABLE_AND_DOWNLOAD_BLOCKED")

    if blockers:
        status = "BLOCKED"
    elif python_path:
        status = "READY_TO_BOOTSTRAP"
    else:
        status = "READY_TO_PROVISION_PYTHON"

    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "run_id": run_id,
        "root": str(root),
        "strategy": strategy,
        "python_path": python_path,
        "managed_python_dir": str(managed),
        "environment": environment,
        "steps": steps,
        "blockers": sorted(set(blockers)),
        "preflight_report_sha256": preflight["report_sha256"],
        "safety": {
            "sudo_allowed": False,
            "system_python_mutation_allowed": False,
            "shell_profile_mutation_allowed": False,
            "root_dependency_mutation_allowed": False,
        },
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan
