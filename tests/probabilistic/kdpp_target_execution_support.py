from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import loto.probabilistic.kdpp_target_execution as target
from loto.probabilistic.kdpp_certification_gate import APPROVAL_TOKEN, sha256_file
from loto.probabilistic.kdpp_history_materializer import (
    approve_history_bundle,
    create_pending_approval,
    materialize_kdpp_history,
)

SHA = "a" * 64
PARQUET_SHA = "b" * 64
REVIEWED_AT = "2026-08-06T04:00:00Z"
_GAME_SPECS = {
    "numbers3": (3, 0, 9),
    "numbers4": (4, 0, 9),
    "miniloto": (5, 1, 31),
    "loto6": (6, 1, 43),
    "loto7": (7, 1, 37),
}


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _history_payload(game: str, draws: int = 8) -> dict[str, object]:
    positions, minimum, maximum = _GAME_SPECS[game]
    columns = [f"N{index}" for index in range(1, positions + 1)]
    rows = []
    span = maximum - minimum + 1
    for draw_no in range(1, draws + 1):
        if game in {"numbers3", "numbers4"}:
            values = {
                column: minimum + ((draw_no + index) % span) for index, column in enumerate(columns)
            }
        else:
            start = minimum + ((draw_no - 1) % (maximum - positions + 1))
            values = {column: start + index for index, column in enumerate(columns)}
        rows.append({"draw_no": draw_no, "values": values})
    return {
        "schema_version": 1,
        "game_id": game,
        "position_columns": columns,
        "rows": rows,
    }


def _raw_handoff(root: Path) -> Path:
    root.mkdir()
    game_bindings: dict[str, object] = {}
    verification_games = []
    copied: dict[str, str] = {}
    for game, (positions, _, maximum) in _GAME_SPECS.items():
        path = root / f"{game}.json"
        _write_json(path, _history_payload(game))
        digest = sha256_file(path)
        copied[path.name] = digest
        game_bindings[game] = {
            "game_id": game,
            "json_path": path.name,
            "json_sha256": digest,
            "parquet_path": f"{game}.parquet",
            "parquet_sha256": PARQUET_SHA,
            "draw_count": 8,
            "position_count": positions,
            "first_ds": "2026-01-01",
            "last_ds": "2026-01-08",
            "observed_min": 0 if game in {"numbers3", "numbers4"} else 1,
            "observed_max": maximum,
        }
        verification_games.append(
            {
                "game_id": game,
                "draw_count": 8,
                "json_sha256": digest,
                "parquet_sha256": PARQUET_SHA,
            }
        )
    verification = {
        "schema_version": 1,
        "status": "VERIFIED",
        "export_root": "/immutable/raw-export",
        "file_count": 14,
        "games": verification_games,
        "future_actuals_used": False,
        "raw_data_modified": False,
    }
    verification_path = root / "history_verification.json"
    _write_json(verification_path, verification)
    copied[verification_path.name] = sha256_file(verification_path)
    approval = {
        "schema_version": 1,
        "status": "APPROVED",
        "approval_scope": "toto2_4m_runtime_request_generation",
        "reviewer": "raw-reviewer",
        "reviewed_at": REVIEWED_AT,
        "review_flags": {
            "source_query_reviewed": True,
            "database_snapshot_reviewed": True,
            "row_counts_reviewed": True,
            "cutoff_dates_reviewed": True,
            "position_ranges_reviewed": True,
        },
        "binding": {
            "schema_version": 1,
            "export_root": "/immutable/raw-export",
            "verification_path": "/evidence/history_verification.json",
            "export_manifest_sha256": SHA,
            "sha256s_sha256": SHA,
            "verification_sha256": sha256_file(verification_path),
            "query_sha256": SHA,
            "database_snapshot_sha256": SHA,
            "source_schema": "dataset",
            "source_table": "loto_y_ts_unified",
            "source_ts_type": "raw",
            "source_mode": "repeatable_read_read_only",
            "future_actuals_used": False,
            "raw_data_modified": False,
            "games": game_bindings,
        },
    }
    approval_path = root / "history_approval.json"
    _write_json(approval_path, approval)
    copied[approval_path.name] = sha256_file(approval_path)
    handoff = {
        "schema_version": 1,
        "status": "MATERIALIZED_APPROVED_HISTORY",
        "materialized_at": "2026-08-06T04:01:00Z",
        "approval_scope": "toto2_4m_runtime_request_generation",
        "approval_sha256": sha256_file(approval_path),
        "verification_sha256": sha256_file(verification_path),
        "export_manifest_sha256": SHA,
        "source_export_root": "/immutable/raw-export",
        "reviewer": "raw-reviewer",
        "reviewed_at": REVIEWED_AT,
        "future_actuals_used": False,
        "raw_data_modified": False,
        "copied_files": copied,
    }
    _write_json(root / "HISTORY_HANDOFF.json", handoff)
    return root


def _confirmations() -> dict[str, bool]:
    return {
        "source_read_only_confirmed": True,
        "train_only_confirmed": True,
        "draw_order_confirmed": True,
        "row_count_confirmed": True,
        "game_geometry_confirmed": True,
        "cutoff_confirmed": True,
        "no_future_actuals_confirmed": True,
        "no_holdout_confirmed": True,
        "no_prospective_confirmed": True,
    }


def _approved_bundle(raw: Path, root: Path) -> tuple[Path, Path]:
    bundle = root / "bundle"
    pending = root / "kdpp.pending.json"
    approved = root / "kdpp.approved.json"
    materialize_kdpp_history(raw, bundle, game="loto7", position=None)
    create_pending_approval(bundle, pending)
    approve_history_bundle(
        bundle,
        pending,
        approved,
        reviewer="kdpp-reviewer",
        reviewed_at_utc="2026-08-06T04:05:00Z",
        approval_token=APPROVAL_TOKEN,
        confirmations=_confirmations(),
    )
    return bundle, approved


def _git(command: list[str], root: Path) -> str:
    completed = subprocess.run(
        ["git", *command], cwd=root, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def _repository(root: Path, required_files: tuple[str, ...]) -> tuple[Path, str]:
    root.mkdir()
    _git(["init", "-b", "test-branch"], root)
    _git(["config", "user.email", "test@example.invalid"], root)
    _git(["config", "user.name", "Test User"], root)
    for relative in required_files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    _git(["add", "."], root)
    _git(["commit", "-m", "fixture"], root)
    return root, _git(["rev-parse", "HEAD"], root)


def _prepared(tmp_path: Path) -> tuple[Path, Path, Path]:
    exporter, exporter_head = _repository(tmp_path / "exporter", target._EXPORTER_FILES)
    kdpp, kdpp_head = _repository(tmp_path / "kdpp", target._KDPP_FILES)
    workspace = tmp_path / "control"
    target.prepare_workspace(
        exporter_repo=exporter,
        exporter_head=exporter_head,
        exporter_python=Path(sys.executable),
        kdpp_repo=kdpp,
        kdpp_head=kdpp_head,
        kdpp_python=Path(sys.executable),
        workspace=workspace,
        run_id="kdpp-target-20260806",
        game="loto7",
        position=None,
        prediction_length=1,
        config_sha256=SHA,
    )
    return workspace, exporter, kdpp
