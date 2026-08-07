from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from loto.probabilistic.kdpp_certification_gate import (
    APPROVAL_TOKEN,
    sha256_file,
    validate_history_bundle,
)
from loto.probabilistic.kdpp_history_materializer import (
    RAW_APPROVAL_SCOPE,
    approve_history_bundle,
    build_indicator_matrix,
    create_pending_approval,
    materialize_kdpp_history,
    parse_game_history,
    tree_sha256,
    validate_materialized_raw_history,
)

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "materialize_kdpp_fixed_k_history.py"
SHA = "a" * 64
PARQUET_SHA = "b" * 64
REVIEWED_AT = "2026-08-06T04:00:00Z"
MATERIALIZED_AT = "2026-08-06T04:01:00Z"

_GAME_SPECS = {
    "numbers3": (3, 0, 9),
    "numbers4": (4, 0, 9),
    "miniloto": (5, 1, 31),
    "loto6": (6, 1, 43),
    "loto7": (7, 1, 37),
}


def _history_payload(game: str, draws: int = 8) -> dict[str, object]:
    positions, minimum, maximum = _GAME_SPECS[game]
    columns = [f"N{index}" for index in range(1, positions + 1)]
    rows = []
    span = maximum - minimum + 1
    for draw_no in range(1, draws + 1):
        if game in {"numbers3", "numbers4"}:
            values = {
                column: minimum + ((draw_no + index) % span)
                for index, column in enumerate(columns)
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


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _raw_handoff(root: Path) -> Path:
    root.mkdir()
    game_bindings: dict[str, object] = {}
    verification_games = []
    copied: dict[str, str] = {}
    for game, (positions, _, _) in _GAME_SPECS.items():
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
            "observed_max": _GAME_SPECS[game][2],
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
        "approval_scope": RAW_APPROVAL_SCOPE,
        "reviewer": "independent-reviewer",
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
        "materialized_at": MATERIALIZED_AT,
        "approval_scope": RAW_APPROVAL_SCOPE,
        "approval_sha256": sha256_file(approval_path),
        "verification_sha256": sha256_file(verification_path),
        "export_manifest_sha256": SHA,
        "source_export_root": "/immutable/raw-export",
        "reviewer": "independent-reviewer",
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


def _approve(bundle: Path, tmp_path: Path) -> Path:
    pending = tmp_path / "pending.json"
    approved = tmp_path / "approved.json"
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
    return approved


def test_validate_materialized_handoff_and_tamper(tmp_path: Path) -> None:
    root = _raw_handoff(tmp_path / "raw")
    handoff, approval, verification = validate_materialized_raw_history(root)
    assert handoff.status == "MATERIALIZED_APPROVED_HISTORY"
    assert approval.status == "APPROVED"
    assert len(verification.games) == 5
    with (root / "loto7.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="SHA-256"):
        validate_materialized_raw_history(root)


@pytest.mark.parametrize(
    ("game", "position", "item_count", "cardinality"),
    [
        ("numbers3", 1, 10, 1),
        ("numbers4", 4, 10, 1),
        ("miniloto", None, 31, 5),
        ("loto6", None, 43, 6),
        ("loto7", None, 37, 7),
    ],
)
def test_materialize_all_geometries(
    tmp_path: Path,
    game: str,
    position: int | None,
    item_count: int,
    cardinality: int,
) -> None:
    raw = _raw_handoff(tmp_path / "raw")
    bundle = tmp_path / "bundle"
    result = materialize_kdpp_history(raw, bundle, game=game, position=position)
    approved = _approve(bundle, tmp_path)
    manifest, _, item_ids = validate_history_bundle(bundle, approved)
    assert result.item_count == item_count
    assert manifest.cardinality == cardinality
    assert len(item_ids) == item_count
    with np.load(bundle / "training.npz", allow_pickle=False) as arrays:
        assert arrays["training_indicators"].shape == (8, item_count)
        assert np.all(arrays["training_indicators"].sum(axis=1) == cardinality)
        assert arrays["draw_nos"].tolist() == list(range(1, 9))


def test_materialization_is_byte_deterministic(tmp_path: Path) -> None:
    raw = _raw_handoff(tmp_path / "raw")
    first = tmp_path / "first"
    second = tmp_path / "second"
    materialize_kdpp_history(raw, first, game="loto7")
    materialize_kdpp_history(raw, second, game="loto7")
    for name in ("history_manifest.json", "item_ids.json", "training.npz", "SHA256SUMS"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert tree_sha256(first) == tree_sha256(second)


def test_numbers_position_and_unordered_position_fail_closed(tmp_path: Path) -> None:
    raw = _raw_handoff(tmp_path / "raw")
    with pytest.raises(ValueError, match="valid position"):
        materialize_kdpp_history(raw, tmp_path / "numbers", game="numbers3")
    with pytest.raises(ValueError, match="do not accept position"):
        materialize_kdpp_history(raw, tmp_path / "loto", game="loto7", position=1)


def test_parse_rejects_draw_gap_and_unsorted_lottery(tmp_path: Path) -> None:
    payload = _history_payload("loto6")
    payload["rows"][2]["draw_no"] = 4  # type: ignore[index]
    path = tmp_path / "gap.json"
    _write_json(path, payload)
    with pytest.raises(ValueError, match="gap-free"):
        parse_game_history(path, game="loto6")
    payload = _history_payload("loto6")
    payload["rows"][0]["values"]["N2"] = 1  # type: ignore[index]
    path = tmp_path / "unsorted.json"
    _write_json(path, payload)
    with pytest.raises(ValueError, match="strictly increasing"):
        parse_game_history(path, game="loto6")


def test_indicator_matrix_semantics() -> None:
    numbers = np.asarray([[1, 2, 3], [4, 5, 6]], dtype=np.int64)
    matrix, item_ids, cardinality, layout = build_indicator_matrix(
        numbers,
        game="numbers3",
        position=2,
    )
    assert item_ids[5] == "n2:5"
    assert matrix[:, 2].tolist() == [1, 0]
    assert matrix[:, 5].tolist() == [0, 1]
    assert cardinality == 1 and layout == "position_local"


def test_pending_approval_detects_bundle_tamper(tmp_path: Path) -> None:
    raw = _raw_handoff(tmp_path / "raw")
    bundle = tmp_path / "bundle"
    materialize_kdpp_history(raw, bundle, game="miniloto")
    pending = tmp_path / "pending.json"
    create_pending_approval(bundle, pending)
    with (bundle / "item_ids.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="no longer matches"):
        approve_history_bundle(
            bundle,
            pending,
            tmp_path / "approved.json",
            reviewer="reviewer",
            reviewed_at_utc="2026-08-06T04:05:00Z",
            approval_token=APPROVAL_TOKEN,
            confirmations=_confirmations(),
        )


def test_approval_requires_all_confirmations_and_token(tmp_path: Path) -> None:
    raw = _raw_handoff(tmp_path / "raw")
    bundle = tmp_path / "bundle"
    materialize_kdpp_history(raw, bundle, game="miniloto")
    pending = tmp_path / "pending.json"
    create_pending_approval(bundle, pending)
    confirmations = _confirmations()
    confirmations["cutoff_confirmed"] = False
    with pytest.raises(ValueError, match="all approval"):
        approve_history_bundle(
            bundle,
            pending,
            tmp_path / "approved.json",
            reviewer="reviewer",
            reviewed_at_utc="2026-08-06T04:05:00Z",
            approval_token=APPROVAL_TOKEN,
            confirmations=confirmations,
        )
    with pytest.raises(ValueError, match="token"):
        approve_history_bundle(
            bundle,
            pending,
            tmp_path / "approved2.json",
            reviewer="reviewer",
            reviewed_at_utc="2026-08-06T04:05:00Z",
            approval_token="WRONG",
            confirmations=_confirmations(),
        )


def test_approval_files_must_be_outside_bundle(tmp_path: Path) -> None:
    raw = _raw_handoff(tmp_path / "raw")
    bundle = tmp_path / "bundle"
    materialize_kdpp_history(raw, bundle, game="loto7")
    with pytest.raises(ValueError, match="outside"):
        create_pending_approval(bundle, bundle / "pending.json")


def test_cli_help_and_materialize(tmp_path: Path) -> None:
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        text=True,
        capture_output=True,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
    assert help_result.returncode == 0
    raw = _raw_handoff(tmp_path / "raw")
    bundle = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "materialize",
            "--source-handoff",
            str(raw),
            "--output-dir",
            str(bundle),
            "--game",
            "numbers4",
            "--position",
            "3",
        ],
        text=True,
        capture_output=True,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "KDPP_HISTORY_BUNDLE_MATERIALIZED"
