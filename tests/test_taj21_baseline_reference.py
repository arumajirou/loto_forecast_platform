from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS, REQUIRED_POINT_METRICS
from loto.game.geometry import known_games

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_PATH = ROOT / "tools" / "evaluation" / "taj21_baseline_campaign.py"
VERIFIER_PATH = ROOT / "tools" / "evaluation" / "taj21_baseline_verify.py"
LAUNCHER_PATH = ROOT / "tools" / "taj21.sh"
SEEDS = (42, 1729, 20260730)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metric_payload() -> dict[str, object]:
    return {
        "hit_at_1": 0.5,
        "position_hit_at_1": 0.5,
        "position_hit_at_1_by_position": {"1": 0.5},
        "all_positions_hit_at_1": 0.0,
        "mae": 1.0,
        "mse": 1.0,
        "rmse": 1.0,
    }


def _seed_summary() -> dict[str, dict[str, object]]:
    return {
        metric: {
            "metric_id": metric,
            "count": 3,
            "mean": 0.5,
            "population_variance": 0.0,
            "standard_deviation": 0.0,
            "minimum": 0.5,
            "maximum": 0.5,
            "worst_value": 0.5,
            "worst_seed": 42,
        }
        for metric in REQUIRED_POINT_METRICS
    }


def _write_fixture(root: Path, *, expose_actuals: bool = False) -> None:
    campaign = root / "campaign"
    campaign.mkdir(parents=True)
    results = []
    for game in known_games():
        for baseline in REQUIRED_BASELINE_IDS:
            candidate_id = f"baseline:{baseline}"
            seed_results = []
            for seed in SEEDS:
                lock = campaign / "prediction_locks" / game / candidate_id / f"seed-{seed}.json"
                lock.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "schema_version": "prediction-lock-v1",
                    "game": game,
                    "candidate_id": candidate_id,
                    "seed": seed,
                    "actuals_known": expose_actuals
                    and game == known_games()[0]
                    and baseline == "random",
                    "predictions": [
                        {"fold_id": "fold-01", "draw_index": 100, "prediction": [1]}
                    ],
                }
                lock.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                seed_results.append(
                    {
                        "seed": seed,
                        "metrics": _metric_payload(),
                        "prediction_lock": {
                            "path": str(lock),
                            "sha256": _sha256(lock),
                        },
                        "runtime_samples": [],
                    }
                )
            results.append(
                {
                    "game": game,
                    "candidate_id": candidate_id,
                    "source": "baseline",
                    "library": "baseline",
                    "task": "position",
                    "status": "SUCCEEDED",
                    "reason": "",
                    "protocol_hash": "a" * 64,
                    "seed_results": seed_results,
                    "seed_summary": _seed_summary(),
                }
            )

    summary = {
        "status": "SUCCEEDED",
        "games": list(known_games()),
        "catalog_models": 0,
        "expected_model_game_pairs": 0,
        "observed_model_game_pairs": 0,
        "matrix_complete": True,
        "primary_metric": "hit_at_1",
        "required_metrics": list(REQUIRED_POINT_METRICS),
        "required_baselines": list(REQUIRED_BASELINE_IDS),
        "seeds": list(SEEDS),
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "results": results,
    }
    (campaign / "campaign_summary.json").write_text(
        json.dumps(summary) + "\n",
        encoding="utf-8",
    )
    (root / "INPUT_MANIFEST.json").write_text(
        json.dumps(
            {
                "schema_version": "taj21-baseline-input-manifest-v1",
                "games": list(known_games()),
                "synthetic": False,
                "raw_files_mutated": False,
                "files": [
                    {
                        "game": game,
                        "filename": f"{game}.csv",
                        "sha256": "0" * 64,
                        "rows": 200,
                    }
                    for game in known_games()
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "BASELINE_REFERENCE.json").write_text(
        json.dumps(
            {
                "schema_version": "taj21-baseline-reference-v1",
                "status": "EXECUTED",
                "synthetic": False,
                "accuracy_claim": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    artifacts = sorted(path for path in root.rglob("*") if path.is_file())
    lines = [f"{_sha256(path)}  {path.relative_to(root).as_posix()}" for path in artifacts]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_launcher_requires_canonical_data_and_has_no_synthetic_fallback() -> None:
    source = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "{preflight|smoke|baselines}" in source
    assert "TAJ21_DATA_DIR" in source
    assert "SYNTHETIC_FALLBACK=FORBIDDEN" in source
    baseline_case = source.split("baselines)", 1)[1]
    assert "--synthetic" not in baseline_case
    assert "taj21_baseline_campaign.py" in baseline_case
    assert "taj21_baseline_verify.py" in baseline_case


def test_campaign_blocks_when_canonical_six_game_inputs_are_missing(tmp_path: Path) -> None:
    campaign = _load(CAMPAIGN_PATH, "taj21_baseline_campaign_test")
    input_dir = tmp_path / "data"
    input_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="missing canonical development CSV"):
        campaign.run_baselines(
            input_dir=input_dir,
            output=tmp_path / "out",
            git_commit="a" * 40,
        )


def test_verifier_accepts_exact_six_game_seven_baseline_matrix(tmp_path: Path) -> None:
    verifier = _load(VERIFIER_PATH, "taj21_baseline_verify_test")
    root = tmp_path / "baseline"
    root.mkdir()
    _write_fixture(root)

    result = verifier.verify_baselines(root)

    assert result["baseline_rows"] == 42
    assert result["prediction_locks"] == 126
    assert result["sha256sums_sha256"] == _sha256(root / "SHA256SUMS")


def test_verifier_rejects_prediction_lock_actual_exposure(tmp_path: Path) -> None:
    verifier = _load(VERIFIER_PATH, "taj21_baseline_verify_actuals_test")
    root = tmp_path / "baseline"
    root.mkdir()
    _write_fixture(root, expose_actuals=True)

    with pytest.raises(ValueError, match="prediction lock exposes actuals"):
        verifier.verify_baselines(root)
