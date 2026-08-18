from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path


def load_tool():
    path = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "phase7_holdout_runner"
        / "frozen_config_forensics.py"
    )
    spec = importlib.util.spec_from_file_location("phase7_frozen_config_forensics", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scan_phase6c_reports_numeric_paths_and_preserves_inputs(tmp_path: Path) -> None:
    tool = load_tool()
    root = tmp_path / "phase6c"
    frozen_dir = root / "artifacts" / "frozen_component_evidence"
    frozen_dir.mkdir(parents=True)

    freeze = {
        "selected_candidate": "catboost_seed_mean",
        "components": [{"seed": seed, "best_trial": 14} for seed in tool.SEEDS],
    }
    freeze_path = root / "artifacts" / "CANDIDATE_FREEZE.json"
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    freeze_sha = hashlib.sha256(freeze_path.read_bytes()).hexdigest()

    source_hashes: dict[Path, str] = {freeze_path: freeze_sha}

    for seed in tool.SEEDS:
        config = {
            "config": {
                "mlf_init_params": {
                    "lags": [1, 2],
                    "lag_transforms": {"1": ["x"]} if seed == 1 else None,
                    "date_features": [],
                    "target_transforms": [],
                    "num_threads": 1,
                },
                "model_params": {"depth": 3},
            }
        }
        config_path = frozen_dir / f"AutoCatboost__seed{seed}__BEST_EFFECTIVE_CONFIG.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        source_hashes[config_path] = hashlib.sha256(config_path.read_bytes()).hexdigest()

        trials_path = frozen_dir / f"AutoCatboost__seed{seed}__optuna_trials.csv"
        with trials_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "number",
                    "params_target_transforms_idx",
                    "params_lags_idx",
                    "params_lag_transforms_idx",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "number": 14,
                    "params_target_transforms_idx": 2,
                    "params_lags_idx": 1,
                    "params_lag_transforms_idx": 0,
                }
            )
        source_hashes[trials_path] = hashlib.sha256(trials_path.read_bytes()).hexdigest()

    output = tmp_path / "out"
    report = tool.scan_phase6c(
        phase6c_root=root,
        output_dir=output,
        expected_freeze_sha256=freeze_sha,
    )

    assert report["status"] == "PASS"
    assert report["seed1_numeric_key_count"] == 1
    assert report["numeric_key_count_total"] == 1
    assert report["duplicate_json_key_count_total"] == 0
    assert report["source_immutability"] == "PASS"
    assert report["replay_executed"] is False
    assert report["holdout_executed"] is False
    assert report["actuals_accessed"] == 0

    numeric_rows = list(
        csv.DictReader(
            (output / "NUMERIC_KEY_PATHS.csv").open(
                "r",
                encoding="utf-8",
                newline="",
            )
        )
    )
    assert numeric_rows == [
        {
            "seed": "1",
            "mapping_path": '$["config"]["mlf_init_params"]["lag_transforms"]',
            "key": "1",
            "value_type": "array",
            "value_preview": '["x"]',
        }
    ]

    for path, expected in source_hashes.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected

    assert (output / "FROZEN_CONFIG_FORENSICS.json").is_file()
    assert (output / "SHA256SUMS").is_file()
