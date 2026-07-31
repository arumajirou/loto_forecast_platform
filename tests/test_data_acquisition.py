from pathlib import Path

import pandas as pd

from loto.data.integrated import acquire_and_build
from loto.data.lotteries import get_lottery_spec
from loto.data.parser import read_csv_flexible
from loto.features.legacy import make_draw_features, make_occurrence_features


def _sample(path: Path) -> None:
    rows = []
    for draw in range(1, 13):
        nums = sorted(((draw * 3 + i * 5) % 37) + 1 for i in range(7))
        nums = sorted(set(nums))
        while len(nums) < 7:
            nums.append(max(nums) + 1)
        rows.append(
            {
                "回号": draw,
                "抽選日": f"2026-01-{draw:02d}",
                **{f"本数字{i + 1}": n for i, n in enumerate(nums[:7])},
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False, encoding="cp932")


def test_flexible_parse_and_integrated_bundle(tmp_path):
    raw = tmp_path / "raw.csv"
    _sample(raw)
    frame, meta = read_csv_flexible(raw)
    assert len(frame) == 12 and meta["encoding"] == "cp932"
    result = acquire_and_build(game="loto7", output_dir=tmp_path / "out", source_file=raw)
    assert result["canonical_manifest"]["row_count"] == 12
    assert Path(result["bundle"]["sqlite"]).exists()
    names = result["bundle"]["tables"]
    assert {
        "draw_features",
        "occurrence_features",
        "canonical_loto7",
        "position_loto7",
        "candidate_features_v2",
    } <= set(names)


def test_legacy_features_cover_original_windows(tmp_path):
    raw = tmp_path / "raw.csv"
    _sample(raw)
    from loto.data.parser import parse_file

    spec = get_lottery_spec("loto7")
    normalized, _ = parse_file(raw, spec)
    draw = make_draw_features(normalized, spec)
    occurrence = make_occurrence_features(normalized, spec)
    assert {"num_sum", "num_prime_count", "num_consecutive_pairs", "ending_entropy"} <= set(
        draw.columns
    )
    assert {
        "freq_last_5",
        "freq_last_10",
        "freq_last_20",
        "freq_last_50",
        "candidate_mod10",
    } <= set(occurrence.columns)
