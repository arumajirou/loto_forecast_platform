from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from loto.evaluation.taj21_artifacts import (
    build_verification_report,
    regenerate_sha256sums,
    write_artifact_manifest,
    write_json,
)
from loto.evaluation.taj21_fold_evidence import (
    augment_fold_and_seed_evidence,
    prediction_before_actual_source_contract,
)
from loto.evaluation.taj21_paired_comparison import build_paired_comparisons
from loto.evaluation.unified_campaign import UnifiedCampaignConfig, run_unified_campaign
from loto.game.geometry import geometry_for


def _synthetic(game: str, *, rows: int = 40, seed: int = 7) -> pd.DataFrame:
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    universe = np.arange(geometry.value_min, geometry.value_max + 1)
    payload = []
    for draw in range(rows):
        if geometry.family == "select":
            values = np.sort(rng.choice(universe, size=geometry.positions, replace=False))
        else:
            values = rng.choice(universe, size=geometry.positions, replace=True)
        payload.append(
            {
                "draw_no": draw + 1,
                **dict(zip(geometry.column_names(), values.tolist(), strict=True)),
            }
        )
    return pd.DataFrame(payload)


def _config(tmp_path: Path) -> UnifiedCampaignConfig:
    return UnifiedCampaignConfig(
        output_dir=tmp_path / "campaign",
        git_commit="1" * 40,
        games=("numbers3",),
        model_ids=("logistic",),
        seeds=(1, 2),
        folds=2,
        test_size=2,
        min_train_size=12,
        holdout_size=4,
        device="cpu",
        max_trials=1,
        parallel_trials=1,
        max_steps=1,
    )


def test_prediction_lock_source_contract_is_fail_closed() -> None:
    contract = prediction_before_actual_source_contract()
    assert contract["prediction_lock_before_target_actual"] is True
    assert contract["prediction_lock_relative_line"] < contract["target_actual_relative_line"]
    assert len(contract["source_sha256"]) == 64


def test_full_evidence_layer_adds_fold_seed_ordering_and_paired_evidence(tmp_path: Path) -> None:
    config = _config(tmp_path)
    frames = {"numbers3": _synthetic("numbers3")}
    summary = run_unified_campaign(frames, config)
    summary = augment_fold_and_seed_evidence(frames, config, summary)

    successful = [row for row in summary["results"] if row["status"] == "SUCCEEDED"]
    assert successful
    for row in successful:
        positions = row["seed_summary"]["position_hit_at_1_by_position"]
        assert len(positions) == geometry_for("numbers3").positions
        assert all(item["count"] == 2 for item in positions.values())
        for seed_result in row["seed_results"]:
            assert len(seed_result["fold_metrics"]) == 2
            evidence = seed_result["actual_read_evidence"]
            assert evidence["verification_actual_read_after_prediction_seal"] is True
            assert evidence["scoring_source_contract"]["prediction_lock_before_target_actual"] is True

    comparisons = build_paired_comparisons(
        summary["results"], config.games, n_boot=50
    )
    rows = comparisons["comparisons"]
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == "logistic"
    assert rows[0]["comparison_status"] == "VALID"
    assert rows[0]["n_pairs"] == 4
    assert 0.0 <= rows[0]["holm_adjusted_p_value"] <= 1.0


def test_formal_artifacts_are_manifested_and_checksummed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    frames = {"numbers3": _synthetic("numbers3")}
    summary = run_unified_campaign(frames, config)
    summary = augment_fold_and_seed_evidence(frames, config, summary)
    comparisons = build_paired_comparisons(
        summary["results"], config.games, n_boot=50
    )
    report = build_verification_report(
        summary,
        comparisons,
        git_commit=config.git_commit,
        folds=config.folds,
    )
    write_json(config.output_dir / "campaign_summary.json", summary)
    write_json(config.output_dir / "PAIRED_COMPARISONS.json", comparisons)
    write_json(
        config.output_dir / "INPUT_MANIFEST.json",
        {
            "schema_version": "test",
            "games": ["numbers3"],
            "files": [],
            "synthetic": False,
            "raw_files_mutated": False,
        },
    )
    write_json(config.output_dir / "VERIFICATION_REPORT.json", report)
    manifest = write_artifact_manifest(config.output_dir, git_commit=config.git_commit)
    sums_sha = regenerate_sha256sums(config.output_dir)

    assert report["status"] == "PASS"
    assert report["fold_evidence_complete"] is True
    assert report["all_seed_per_position_summary_complete"] is True
    assert report["post_seal_actual_read_evidence_complete"] is True
    assert manifest["entries"]
    assert len(sums_sha) == 64
    assert (config.output_dir / "ARTIFACT_MANIFEST.json").is_file()
    assert (config.output_dir / "SHA256SUMS").is_file()


def test_formal_runner_uses_shared_parser_and_forbids_synthetic_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    runner = (root / "tools/evaluation/taj21_full_campaign.py").read_text(encoding="utf-8")
    launcher = (root / "tools/taj21_full.sh").read_text(encoding="utf-8")
    assert "parse_file(path, spec)" in runner
    assert "pd.read_csv(path)" not in runner
    assert "TAJ21_DATA_DIR" in launcher
    assert "SYNTHETIC_FALLBACK=FORBIDDEN" in launcher
    assert "--synthetic" not in launcher
