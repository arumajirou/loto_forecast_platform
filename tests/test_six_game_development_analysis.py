from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


def _load_runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_six_game_development_analysis.py"
    spec = importlib.util.spec_from_file_location("six_game_development_analysis", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_game(
    root: Path,
    *,
    game: str,
    columns: tuple[str, ...],
    rows: int = 80,
) -> None:
    target = root / game / "normalized"
    target.mkdir(parents=True)
    frame: dict[str, object] = {
        "draw_date": pd.date_range("2020-01-01", periods=rows, freq="D"),
    }
    if columns[0].startswith("n"):
        # Keep the lotto/bingo representation ordered while varying every position.
        base = [(index % 5) + 1 for index in range(rows)]
        for offset, column in enumerate(columns):
            frame[column] = [value + offset * 5 for value in base]
    else:
        for offset, column in enumerate(columns):
            frame[column] = [(index + offset * 3) % 10 for index in range(rows)]
    pd.DataFrame(frame).to_csv(target / f"{game}.csv", index=False)


def _build_data_root(tmp_path: Path, module) -> Path:
    data_root = tmp_path / "data"
    for game, columns in module.GAME_COLUMNS.items():
        _write_game(data_root, game=game, columns=columns)
    return data_root


def test_six_game_campaign_counts_and_keeps_holdout_closed(tmp_path: Path) -> None:
    module = _load_runner_module()
    data_root = _build_data_root(tmp_path, module)
    output = tmp_path / "out"

    rc = module.main(
        [
            "--data-root",
            str(data_root),
            "--output",
            str(output),
            "--holdout-size",
            "10",
            "--lags",
            "3",
            "--min-segment",
            "10",
            "--permutations",
            "19",
            "--seed",
            "7",
        ]
    )

    assert rc == 0
    summary = json.loads((output / "CAMPAIGN_SUMMARY.json").read_text())
    manifest = json.loads((output / "DATASET_MANIFEST.json").read_text())
    temporal = json.loads((output / "TEMPORAL_TESTS.json").read_text())
    associations = json.loads((output / "ASSOCIATION_TESTS.json").read_text())
    omnibus = json.loads((output / "MULTIPLICITY_OMNIBUS.json").read_text())

    assert summary["status"] == "SUCCEEDED"
    assert summary["games"] == 6
    assert summary["position_series"] == 33
    assert summary["temporal_hypotheses"] == 99
    assert summary["association_pairs"] == 83
    assert summary["association_hypotheses"] == 166
    assert summary["omnibus_hypotheses"] == 265
    assert summary["holdout_evaluated"] is False
    assert summary["prospective_evaluated"] is False
    assert summary["promotion"] is False
    assert summary["causal_claim"] is False
    assert len(temporal) == 99
    assert len(associations) == 166
    assert len(omnibus) == 265

    assert len(manifest) == 6
    assert all(row["input_rows"] == 80 for row in manifest)
    assert all(row["development_rows"] == 70 for row in manifest)
    assert all(row["holdout_rows"] == 10 for row in manifest)
    assert all(row["holdout_access"] == "split_only_not_analyzed" for row in manifest)

    sorted_rows = [row for row in associations if row["game"] == "loto7"]
    number_rows = [row for row in associations if row["game"] == "numbers4"]
    assert sorted_rows
    assert number_rows
    assert all(row["representation"] == "sorted_position" for row in sorted_rows)
    assert all(row["structural_warning"] for row in sorted_rows)
    assert all(row["causal_claim_eligible"] is False for row in associations)
    assert all(row["structural_warning"] is None for row in number_rows)

    checksums = (output / "SHA256SUMS").read_text().splitlines()
    assert any(line.endswith("  CAMPAIGN_SUMMARY.json") for line in checksums)
    assert any(line.endswith("  ASSOCIATION_TESTS.csv") for line in checksums)


def test_six_game_campaign_fails_closed_without_complete_root(tmp_path: Path) -> None:
    module = _load_runner_module()
    data_root = _build_data_root(tmp_path, module)
    (data_root / "bingo5" / "normalized" / "bingo5.csv").unlink()

    with pytest.raises(FileNotFoundError):
        module.main(
            [
                "--data-root",
                str(data_root),
                "--output",
                str(tmp_path / "out"),
                "--holdout-size",
                "10",
                "--permutations",
                "9",
            ]
        )


def test_six_game_campaign_refuses_nonpositive_holdout(tmp_path: Path) -> None:
    module = _load_runner_module()
    data_root = _build_data_root(tmp_path, module)

    with pytest.raises(ValueError, match="holdout-size"):
        module.main(
            [
                "--data-root",
                str(data_root),
                "--output",
                str(tmp_path / "out"),
                "--holdout-size",
                "0",
            ]
        )
