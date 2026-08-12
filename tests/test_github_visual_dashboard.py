from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_github_visual_dashboard import (
    DashboardBuildError,
    build_dashboard_payload,
)


def _observability() -> dict[str, object]:
    return {
        "schema_version": 1,
        "repository": "example/repo",
        "main_sha": "a" * 40,
        "project_url": "https://github.com/users/example/projects/1",
        "open_issue_count": 1,
        "open_pr_count": 2,
        "active_workflow_count": 1,
        "open_issues": [
            {
                "number": 7,
                "title": "runtime blocker",
                "html_url": "https://github.com/example/repo/issues/7",
                "labels": ["bug"],
                "assignees": [],
                "updated_at": "2026-08-12T00:00:00Z",
            }
        ],
        "active_workflows": [
            {
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "html_url": "https://github.com/example/repo/actions/workflows/ci.yml",
            }
        ],
    }


def _identity_summary() -> dict[str, object]:
    return {
        "schema_version": 1,
        "unified_catalog_identities": 2,
        "canonical_games": ["numbers3", "numbers4"],
        "unified_model_game_cross_product": 4,
    }


def _catalog() -> list[dict[str, object]]:
    return [
        {
            "model_id": "model-a",
            "library": "lib-a",
            "catalog_source": "existing",
        },
        {
            "model_id": "model-b",
            "library": "lib-b",
            "catalog_source": "probabilistic",
        },
    ]


def _write_evidence(path: Path, records: list[dict[str, str]]) -> Path:
    path.write_text(
        json.dumps({"schema_version": 1, "records": records}),
        encoding="utf-8",
    )
    return path


def test_missing_runtime_evidence_remains_unassessed() -> None:
    payload = build_dashboard_payload(
        _observability(),
        _identity_summary(),
        _catalog(),
    )

    assert len(payload["cells"]) == 4
    assert payload["status_counts"] == {"UNASSESSED": 4}
    assert {cell["status"] for cell in payload["cells"]} == {"UNASSESSED"}
    assert payload["formal_gates"] == {
        "holdout": "CLOSED",
        "prospective": "CLOSED",
        "automatic_promotion": "FORBIDDEN",
    }


def test_exact_runtime_evidence_updates_only_matching_cell(tmp_path: Path) -> None:
    evidence = _write_evidence(
        tmp_path / "runtime.json",
        [
            {
                "model_id": "model-a",
                "game": "numbers3",
                "status": "RUNTIME_CERTIFIED",
                "evidence_ref": "run://runtime-a",
                "git_sha": "b" * 40,
            }
        ],
    )

    payload = build_dashboard_payload(
        _observability(),
        _identity_summary(),
        _catalog(),
        evidence,
    )

    cells = {(cell["model_id"], cell["game"]): cell for cell in payload["cells"]}
    assert cells[("model-a", "numbers3")]["status"] == "RUNTIME_CERTIFIED"
    assert cells[("model-a", "numbers4")]["status"] == "UNASSESSED"
    assert payload["status_counts"] == {
        "RUNTIME_CERTIFIED": 1,
        "UNASSESSED": 3,
    }


def test_unknown_runtime_evidence_fails_closed(tmp_path: Path) -> None:
    evidence = _write_evidence(
        tmp_path / "runtime.json",
        [
            {
                "model_id": "unknown",
                "game": "numbers3",
                "status": "RUNTIME_CERTIFIED",
                "evidence_ref": "run://unknown",
                "git_sha": "c" * 40,
            }
        ],
    )

    with pytest.raises(DashboardBuildError, match="unknown model-game pair"):
        build_dashboard_payload(
            _observability(),
            _identity_summary(),
            _catalog(),
            evidence,
        )


def test_duplicate_catalog_identity_fails_closed() -> None:
    catalog = _catalog()
    catalog[1]["model_id"] = "model-a"

    with pytest.raises(DashboardBuildError, match="duplicate model_id"):
        build_dashboard_payload(
            _observability(),
            _identity_summary(),
            catalog,
        )


def test_cross_product_mismatch_fails_closed() -> None:
    summary = _identity_summary()
    summary["unified_model_game_cross_product"] = 999

    with pytest.raises(DashboardBuildError, match="cross-product mismatch"):
        build_dashboard_payload(
            _observability(),
            summary,
            _catalog(),
        )


def test_client_avoids_dynamic_inner_html() -> None:
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "github-dashboard" / "assets" / "app.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in javascript
    assert ".textContent" in javascript
