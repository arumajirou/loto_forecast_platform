from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.analysis.dependence import ljung_box_test, pearson_association, spearman_association
from loto.analysis.multiple_testing import (
    adjust_hypotheses,
    benjamini_hochberg_adjust,
    holm_adjust,
)
from loto.analysis.trends import linear_trend, mean_shift_scan
from loto.evaluation.multiplicity import benjamini_hochberg as canonical_bh
from loto.evaluation.multiplicity import holm as canonical_holm


def test_association_is_strong_but_never_causal() -> None:
    x = np.arange(1.0, 31.0)
    y = 3.0 * x + 7.0

    pearson = pearson_association(x, y, representation="sorted_position")
    spearman = spearman_association(x, y, representation="sorted_position")

    assert pearson.statistic == pytest.approx(1.0)
    assert spearman.statistic == pytest.approx(1.0)
    assert pearson.p_value < 1e-20
    assert spearman.p_value < 1e-20
    assert pearson.representation == "sorted_position"
    assert pearson.causal_claim_eligible is False
    assert spearman.causal_claim_eligible is False


def test_ljung_box_detects_strong_serial_dependence() -> None:
    values = np.sin(np.linspace(0.0, 16.0, 240))
    result = ljung_box_test(values, lags=8)

    assert result.statistic > 100.0
    assert result.p_value < 1e-20
    assert len(result.autocorrelations) == 8
    assert result.causal_claim_eligible is False


def test_linear_trend_and_mean_shift_scan_are_deterministic() -> None:
    trend = linear_trend(np.arange(50.0))
    assert trend.slope == pytest.approx(1.0)
    assert trend.r_value == pytest.approx(1.0)
    assert trend.p_value < 1e-20

    values = np.concatenate([np.zeros(30), np.full(30, 10.0)])
    first = mean_shift_scan(values, min_segment=10, repetitions=199, seed=7)
    second = mean_shift_scan(values, min_segment=10, repetitions=199, seed=7)

    assert first == second
    assert first.split_index == 30
    assert first.mean_shift == pytest.approx(10.0)
    assert first.absolute_mean_shift == pytest.approx(10.0)
    assert first.permutation_p_value <= 0.01
    assert first.causal_claim_eligible is False


def test_holm_and_bh_adjustment_preserve_original_order_and_canonical_parity() -> None:
    p_values = [0.01, 0.04, 0.03]

    holm = holm_adjust(p_values)
    bh = benjamini_hochberg_adjust(p_values)
    assert holm == pytest.approx([0.03, 0.06, 0.06])
    assert bh == pytest.approx([0.03, 0.04, 0.04])
    assert holm == pytest.approx(canonical_holm(p_values).adjusted_p)
    assert bh == pytest.approx(canonical_bh(p_values).adjusted_p)

    rows = adjust_hypotheses(
        ["a", "b", "c"],
        p_values,
        method="holm",
        alpha=0.05,
    )
    assert [row.hypothesis_id for row in rows] == ["a", "b", "c"]
    assert [row.rejected for row in rows] == [True, False, False]


def _load_runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_statistical_causal_analysis.py"
    spec = importlib.util.spec_from_file_location("scientific_analysis_runner", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_writes_hashed_development_only_evidence(tmp_path: Path) -> None:
    module = _load_runner_module()
    input_path = tmp_path / "series.csv"
    output = tmp_path / "out"
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2020-01-01", periods=80, freq="D"),
            "value": np.concatenate([np.zeros(40), np.full(40, 5.0)]),
            "associate": np.arange(80.0),
        }
    )
    frame.to_csv(input_path, index=False)

    rc = module.main(
        [
            "--input",
            str(input_path),
            "--value-column",
            "value",
            "--association-columns",
            "associate",
            "--time-column",
            "time",
            "--representation",
            "draw_aggregate",
            "--holdout-size",
            "10",
            "--lags",
            "5",
            "--min-segment",
            "10",
            "--permutations",
            "49",
            "--seed",
            "3",
            "--event-index",
            "40",
            "--pre-window",
            "10",
            "--post-window",
            "10",
            "--max-placebos",
            "20",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    summary = json.loads((output / "SUMMARY.json").read_text())
    config = json.loads((output / "CONFIG.json").read_text())
    assert summary["status"] == "ANALYSIS_COMPLETE"
    assert summary["input_rows"] == 80
    assert summary["rows"] == 70
    assert summary["holdout_rows"] == 10
    assert summary["causal_evidence_gate"] is False
    assert config["input_rows"] == 80
    assert config["analyzed_rows"] == 70
    assert config["holdout_rows"] == 10
    assert config["holdout_start_index"] == 70
    assert config["holdout_access"] == "split_only_not_analyzed"
    assert config["holdout_evaluated"] is False
    assert config["prospective_evaluated"] is False
    assert config["promotion"] is False
    assert (output / "MULTIPLE_TESTING.json").is_file()
    assert (output / "PLACEBO_FALSIFICATION.json").is_file()
    checksums = (output / "SHA256SUMS").read_text().splitlines()
    assert any(line.endswith("  SUMMARY.json") for line in checksums)


def test_runner_refuses_development_label_without_physical_holdout(tmp_path: Path) -> None:
    module = _load_runner_module()
    input_path = tmp_path / "series.csv"
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2020-01-01", periods=40, freq="D"),
            "value": np.arange(40.0),
        }
    )
    frame.to_csv(input_path, index=False)

    with pytest.raises(ValueError, match="requires a positive --holdout-size"):
        module.main(
            [
                "--input",
                str(input_path),
                "--value-column",
                "value",
                "--time-column",
                "time",
                "--output",
                str(tmp_path / "out"),
            ]
        )
