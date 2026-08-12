#!/usr/bin/env python3
"""Build a static, evidence-aware GitHub visual dashboard."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

ALLOWED_RUNTIME_STATUSES = {
    "RUNTIME_CERTIFIED",
    "RUNTIME_FAILED",
    "BLOCKED",
    "UNSUPPORTED",
    "NON_ROUTABLE",
}
SUPPORTED_OBSERVABILITY_SCHEMA_VERSIONS = {1, 2}
FORMAL_GATES = {
    "holdout": "CLOSED",
    "prospective": "CLOSED",
    "automatic_promotion": "FORBIDDEN",
}


class DashboardBuildError(ValueError):
    """Raised when dashboard source data is ambiguous or unsafe."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardBuildError(f"cannot read JSON {path}: {exc}") from exc


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DashboardBuildError(f"{name} must be a JSON object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise DashboardBuildError(f"{name} must be a JSON array")
    return value


def _required_text(row: dict[str, Any], field: str, context: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DashboardBuildError(f"{context}.{field} must be non-empty text")
    return value.strip()


def _validate_observability(payload: dict[str, Any]) -> None:
    version = payload.get("schema_version")
    if version not in SUPPORTED_OBSERVABILITY_SCHEMA_VERSIONS:
        supported = ", ".join(str(item) for item in sorted(SUPPORTED_OBSERVABILITY_SCHEMA_VERSIONS))
        raise DashboardBuildError(
            f"observability schema_version must be one of: {supported}"
        )
    _required_text(payload, "repository", "observability")
    _required_text(payload, "main_sha", "observability")
    _require_list(payload.get("open_issues"), "observability.open_issues")
    _require_list(payload.get("active_workflows"), "observability.active_workflows")


def _validate_identity_inputs(
    summary: dict[str, Any],
    catalog: list[Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    if summary.get("schema_version") != 1:
        raise DashboardBuildError("identity summary schema_version must be 1")

    raw_games = _require_list(summary.get("canonical_games"), "canonical_games")
    games = [str(game).strip() for game in raw_games]
    if not games or any(not game for game in games) or len(set(games)) != len(games):
        raise DashboardBuildError("canonical_games must be unique non-empty values")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(catalog):
        row = _require_mapping(raw, f"catalog[{index}]")
        model_id = _required_text(row, "model_id", f"catalog[{index}]")
        if model_id in seen:
            raise DashboardBuildError(f"duplicate model_id: {model_id}")
        seen.add(model_id)
        normalized.append(
            {
                "model_id": model_id,
                "library": str(row.get("library") or "unknown"),
                "catalog_source": str(row.get("catalog_source") or "unknown"),
                "family": str(row.get("family") or ""),
            }
        )

    expected_models = summary.get("unified_catalog_identities")
    if expected_models != len(normalized):
        message = (
            f"unified catalog count mismatch: summary={expected_models!r}, actual={len(normalized)}"
        )
        raise DashboardBuildError(message)
    expected_pairs = summary.get("unified_model_game_cross_product")
    actual_pairs = len(normalized) * len(games)
    if expected_pairs != actual_pairs:
        message = (
            f"model-game cross-product mismatch: summary={expected_pairs!r}, actual={actual_pairs}"
        )
        raise DashboardBuildError(message)
    return games, normalized


def _apply_runtime_evidence(
    cells: dict[tuple[str, str], dict[str, Any]],
    path: Path | None,
) -> None:
    if path is None:
        return

    payload = _require_mapping(_load_json(path), "runtime evidence")
    if payload.get("schema_version") != 1:
        raise DashboardBuildError("runtime evidence schema_version must be 1")
    records = _require_list(payload.get("records"), "runtime evidence.records")
    seen: set[tuple[str, str]] = set()

    for index, raw in enumerate(records):
        row = _require_mapping(raw, f"runtime evidence.records[{index}]")
        model_id = _required_text(row, "model_id", f"runtime evidence.records[{index}]")
        game = _required_text(row, "game", f"runtime evidence.records[{index}]")
        status = _required_text(row, "status", f"runtime evidence.records[{index}]")
        evidence_ref = _required_text(
            row,
            "evidence_ref",
            f"runtime evidence.records[{index}]",
        )
        git_sha = _required_text(row, "git_sha", f"runtime evidence.records[{index}]")
        if status not in ALLOWED_RUNTIME_STATUSES:
            raise DashboardBuildError(f"unsupported runtime status: {status}")
        key = (model_id, game)
        if key not in cells:
            raise DashboardBuildError(
                f"runtime evidence targets unknown model-game pair: {model_id}/{game}"
            )
        if key in seen:
            raise DashboardBuildError(
                f"duplicate runtime evidence for model-game pair: {model_id}/{game}"
            )
        seen.add(key)
        cells[key]["status"] = status
        cells[key]["evidence_ref"] = evidence_ref
        cells[key]["git_sha"] = git_sha


def build_dashboard_payload(
    observability: dict[str, Any],
    identity_summary: dict[str, Any],
    unified_catalog: list[Any],
    runtime_evidence: Path | None = None,
) -> dict[str, Any]:
    _validate_observability(observability)
    games, models = _validate_identity_inputs(identity_summary, unified_catalog)

    cell_map: dict[tuple[str, str], dict[str, Any]] = {}
    cells: list[dict[str, Any]] = []
    for model in models:
        for game in games:
            cell = {
                **model,
                "game": game,
                "status": "UNASSESSED",
                "evidence_ref": None,
                "git_sha": None,
            }
            cell_map[(model["model_id"], game)] = cell
            cells.append(cell)

    _apply_runtime_evidence(cell_map, runtime_evidence)
    counts = Counter(str(cell["status"]) for cell in cells)

    return {
        "schema_version": 1,
        "dashboard_semantics": (
            "Model-game cells are planning units. UNASSESSED means no exact runtime "
            "evidence was supplied to this build; it is not a failure."
        ),
        "repository": observability["repository"],
        "main_sha": observability["main_sha"],
        "project_url": observability.get("project_url"),
        "open_issue_count": observability.get("open_issue_count", 0),
        "open_pr_count": observability.get("open_pr_count", 0),
        "active_workflow_count": observability.get("active_workflow_count", 0),
        "open_issues": observability["open_issues"],
        "active_workflows": observability["active_workflows"],
        "formal_gates": dict(FORMAL_GATES),
        "identity_summary": {
            "unified_catalog_identities": len(models),
            "canonical_games": games,
            "model_game_cross_product": len(cells),
        },
        "status_counts": dict(sorted(counts.items())),
        "models": models,
        "cells": cells,
    }


def _copy_site_assets(source_dir: Path, output_dir: Path) -> None:
    required = ("index.html", "assets/app.js", "assets/styles.css")
    for relative in required:
        source = source_dir / relative
        if not source.is_file():
            raise DashboardBuildError(f"missing dashboard asset: {source}")
        destination = output_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observability-json", type=Path, required=True)
    parser.add_argument("--identity-summary-json", type=Path, required=True)
    parser.add_argument("--unified-catalog-json", type=Path, required=True)
    parser.add_argument("--runtime-evidence-json", type=Path)
    parser.add_argument("--source-dir", type=Path, default=Path("github-dashboard"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    observability = _require_mapping(_load_json(args.observability_json), "observability")
    identity_summary = _require_mapping(
        _load_json(args.identity_summary_json), "identity summary"
    )
    unified_catalog = _require_list(_load_json(args.unified_catalog_json), "unified catalog")

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True)

    payload = build_dashboard_payload(
        observability,
        identity_summary,
        unified_catalog,
        args.runtime_evidence_json,
    )
    _copy_site_assets(args.source_dir, args.output_dir)
    _write_json(args.output_dir / "data" / "dashboard.json", payload)
    (args.output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
