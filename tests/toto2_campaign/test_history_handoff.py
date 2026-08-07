from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.toto2_campaign import history_handoff
from loto.toto2_campaign.history_handoff import (
    APPROVAL_TOKEN,
    ReviewFlags,
    approve_pending,
    build_export_binding,
    create_pending_approval,
    materialize_approved_histories,
    validate_approved_handoff,
)
from loto.toto2_campaign.raw_history_export import FORMAL_GAMES, sha256_file


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    export_root = tmp_path / "export"
    export_root.mkdir()
    (export_root / "RAW_QUERY.sql").write_text("SELECT 1;\n", encoding="utf-8")
    _write_json(
        export_root / "DATABASE_SNAPSHOT.json",
        {
            "transaction_read_only": True,
            "transaction_isolation": "repeatable read",
        },
    )

    manifest_games: dict[str, object] = {}
    verification_games: list[dict[str, object]] = []
    for index, game_id in enumerate(FORMAL_GAMES, start=1):
        json_path = export_root / f"{game_id}.json"
        parquet_path = export_root / f"{game_id}.parquet"
        _write_json(
            json_path,
            {
                "schema_version": 1,
                "game_id": game_id,
                "position_columns": ["N1"],
                "rows": [{"draw_no": 1, "values": {"N1": index}}],
            },
        )
        parquet_path.write_bytes(f"parquet-{game_id}".encode())
        json_sha = sha256_file(json_path)
        parquet_sha = sha256_file(parquet_path)
        manifest_games[game_id] = {
            "draw_count": 512 + index,
            "position_count": index + 2,
            "first_ds": "2000-01-01",
            "last_ds": f"2026-08-0{index}",
            "observed_min": 0 if game_id.startswith("numbers") else 1,
            "observed_max": 9 if game_id.startswith("numbers") else 31 + index,
            "json_sha256": json_sha,
            "parquet_sha256": parquet_sha,
        }
        verification_games.append(
            {
                "game_id": game_id,
                "draw_count": 512 + index,
                "json_sha256": json_sha,
                "parquet_sha256": parquet_sha,
            }
        )

    _write_json(
        export_root / "EXPORT_MANIFEST.json",
        {
            "schema_version": 1,
            "source_schema": "dataset",
            "source_table": "loto_y_ts_unified",
            "source_ts_type": "raw",
            "source_mode": "repeatable_read_read_only",
            "future_actuals_used": False,
            "games": manifest_games,
        },
    )
    (export_root / "SHA256SUMS").write_text("sealed\n", encoding="utf-8")

    verification_path = tmp_path / "verification.json"
    verification = {
        "schema_version": 1,
        "status": "VERIFIED",
        "export_root": str(export_root.resolve()),
        "file_count": 14,
        "games": verification_games,
        "future_actuals_used": False,
        "raw_data_modified": False,
    }
    _write_json(verification_path, verification)
    monkeypatch.setattr(history_handoff, "verify_export_bundle", lambda root: verification)
    return export_root, verification_path


def _confirmed_flags() -> ReviewFlags:
    return ReviewFlags(
        source_query_reviewed=True,
        database_snapshot_reviewed=True,
        row_counts_reviewed=True,
        cutoff_dates_reviewed=True,
        position_ranges_reviewed=True,
    )


def _approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    export_root, verification = _make_export(tmp_path, monkeypatch)
    pending = tmp_path / "pending.json"
    approved = tmp_path / "approved.json"
    create_pending_approval(export_root, verification, pending)
    approve_pending(
        export_root,
        verification,
        pending,
        approved,
        reviewer="target-host-operator",
        reviewed_at="2026-08-06T01:30:00Z",
        approval_token=APPROVAL_TOKEN,
        review_flags=_confirmed_flags(),
    )
    return export_root, verification, approved


def test_pending_record_is_bound_but_not_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification = _make_export(tmp_path, monkeypatch)
    pending_path = tmp_path / "pending.json"
    pending = create_pending_approval(export_root, verification, pending_path)

    assert pending.status == "PENDING"
    assert pending.binding.games["loto7"].last_ds == "2026-08-05"
    with pytest.raises(ValueError, match="status must be APPROVED"):
        validate_approved_handoff(export_root, verification, pending_path)


def test_wrong_approval_token_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification = _make_export(tmp_path, monkeypatch)
    pending = tmp_path / "pending.json"
    create_pending_approval(export_root, verification, pending)

    with pytest.raises(ValueError, match="token mismatch"):
        approve_pending(
            export_root,
            verification,
            pending,
            tmp_path / "approved.json",
            reviewer="operator",
            reviewed_at="2026-08-06T01:30:00Z",
            approval_token="WRONG",
            review_flags=_confirmed_flags(),
        )


def test_all_review_confirmations_are_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification = _make_export(tmp_path, monkeypatch)
    pending = tmp_path / "pending.json"
    create_pending_approval(export_root, verification, pending)
    flags = _confirmed_flags().model_copy(update={"cutoff_dates_reviewed": False})

    with pytest.raises(ValueError, match="all history review flags"):
        approve_pending(
            export_root,
            verification,
            pending,
            tmp_path / "approved.json",
            reviewer="operator",
            reviewed_at="2026-08-06T01:30:00Z",
            approval_token=APPROVAL_TOKEN,
            review_flags=flags,
        )


def test_approved_record_validates_against_fresh_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification, approved = _approved(tmp_path, monkeypatch)

    result = validate_approved_handoff(export_root, verification, approved)

    assert result.status == "APPROVED"
    assert result.reviewer == "target-host-operator"
    assert set(result.binding.games) == set(FORMAL_GAMES)


def test_export_tamper_after_approval_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification, approved = _approved(tmp_path, monkeypatch)
    (export_root / "loto7.json").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        validate_approved_handoff(export_root, verification, approved)


def test_verification_tamper_after_approval_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification, approved = _approved(tmp_path, monkeypatch)
    payload = json.loads(verification.read_text(encoding="utf-8"))
    payload["file_count"] = 999
    _write_json(verification, payload)

    with pytest.raises(ValueError, match="saved verification differs"):
        validate_approved_handoff(export_root, verification, approved)


def test_materialization_copies_only_approved_inputs_and_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification, approved = _approved(tmp_path, monkeypatch)
    destination = tmp_path / "approved-history"

    handoff = materialize_approved_histories(
        export_root,
        verification,
        approved,
        destination,
    )

    expected = {
        *{f"{game}.json" for game in FORMAL_GAMES},
        "history_verification.json",
        "history_approval.json",
        "HISTORY_HANDOFF.json",
    }
    assert {path.name for path in destination.iterdir()} == expected
    assert handoff["status"] == "MATERIALIZED_APPROVED_HISTORY"
    assert handoff["future_actuals_used"] is False
    for game_id in FORMAL_GAMES:
        assert sha256_file(destination / f"{game_id}.json") == build_export_binding(
            export_root,
            verification,
        ).games[game_id].json_sha256


def test_approval_and_verification_cannot_be_inside_export_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root, verification = _make_export(tmp_path, monkeypatch)
    inside = export_root / "pending.json"

    with pytest.raises(ValueError, match="outside the immutable export root"):
        create_pending_approval(export_root, verification, inside)
