from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from loto.data.payouts import (
    PayoutColumnMap,
    RawPayoutSnapshot,
    materialize_raw_payout_snapshot,
    normalize_payout_dataframe,
    write_payout_facts,
)


def _snapshot(tmp_path: Path) -> RawPayoutSnapshot:
    return materialize_raw_payout_snapshot(
        b"draw,tier,winners\n1,1,2\n",
        tmp_path / "raw",
        source_url="https://example.invalid/primary-source",
        observed_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
        content_type="text/csv",
        parser_version="test-source-v1",
        raw_filename="source.csv",
    )


def test_raw_snapshot_is_single_use_and_self_describing(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    root = tmp_path / "raw"

    assert snapshot.raw_sha256 == hashlib.sha256((root / "source.csv").read_bytes()).hexdigest()
    assert (root / "snapshot.json").is_file()
    sums = (root / "SHA256SUMS").read_text(encoding="utf-8")
    assert "source.csv" in sums and "snapshot.json" in sums

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        materialize_raw_payout_snapshot(
            b"different",
            root,
            source_url=snapshot.source_url,
            observed_at=snapshot.observed_at,
            content_type="text/csv",
            parser_version=snapshot.parser_version,
        )


def test_snapshot_requires_timezone_aware_observation() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        RawPayoutSnapshot(
            source_url="https://example.invalid",
            observed_at=datetime(2026, 8, 10, 9, 0),
            content_type="text/csv",
            parser_version="v1",
            raw_filename="source.csv",
            raw_sha256="0" * 64,
            raw_bytes=1,
        )


def test_explicit_mapping_normalizes_japanese_numeric_text(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    frame = pd.DataFrame(
        [
            {
                "回号": "123回",
                "等級": "1等",
                "口数": "1,234口",
                "賞金": "200,000円",
                "販売額": "3,000,000円",
                "キャリー": "0円",
                "日付": "2026-08-10",
            },
            {
                "回号": "123回",
                "等級": "2等",
                "口数": "12口",
                "賞金": "30,000円",
                "販売額": "3,000,000円",
                "キャリー": pd.NA,
                "日付": "2026-08-10",
            },
        ]
    )
    columns = PayoutColumnMap(
        draw_no="回号",
        tier="等級",
        winner_count="口数",
        prize_per_winner_jpy="賞金",
        sales_amount_jpy="販売額",
        carryover_jpy="キャリー",
        draw_date="日付",
    )

    facts = normalize_payout_dataframe(frame, game="loto6", columns=columns, snapshot=snapshot)

    assert len(facts) == 2
    assert facts[0].draw_no == 123
    assert facts[0].winner_count == 1234
    assert facts[0].prize_per_winner_jpy == 200_000
    assert facts[0].sales_amount_jpy == 3_000_000
    assert facts[0].carryover_jpy == 0
    assert facts[1].carryover_jpy is None
    assert facts[0].raw_sha256 == snapshot.raw_sha256


def test_mapping_fails_closed_on_missing_duplicate_and_negative_values(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    columns = PayoutColumnMap(draw_no="draw", tier="tier", winner_count="winners")

    with pytest.raises(ValueError, match="missing required"):
        normalize_payout_dataframe(
            pd.DataFrame([{"draw": 1, "tier": "1"}]),
            game="numbers3",
            columns=columns,
            snapshot=snapshot,
        )

    with pytest.raises(ValueError, match="duplicate payout fact key"):
        normalize_payout_dataframe(
            pd.DataFrame(
                [
                    {"draw": 1, "tier": "1", "winners": 2},
                    {"draw": 1, "tier": "1", "winners": 3},
                ]
            ),
            game="numbers3",
            columns=columns,
            snapshot=snapshot,
        )

    with pytest.raises(ValueError, match="non-negative"):
        normalize_payout_dataframe(
            pd.DataFrame([{"draw": 1, "tier": "1", "winners": -1}]),
            game="numbers3",
            columns=columns,
            snapshot=snapshot,
        )


def test_normalized_bundle_writes_jsonl_parquet_manifest_and_checksums(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    columns = PayoutColumnMap(draw_no="draw", tier="tier", winner_count="winners")
    facts = normalize_payout_dataframe(
        pd.DataFrame([{"draw": 1, "tier": "1", "winners": 2}]),
        game="numbers3",
        columns=columns,
        snapshot=snapshot,
    )

    result = write_payout_facts(facts, tmp_path / "normalized")
    root = tmp_path / "normalized"

    assert result["rows"] == 1
    assert (root / "payout_facts.jsonl").is_file()
    assert (root / "payout_facts.parquet").is_file()
    assert (root / "ARTIFACT_MANIFEST.json").is_file()
    sums = (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(sums) == 3
    for line in sums:
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_payout_facts(facts, root)
