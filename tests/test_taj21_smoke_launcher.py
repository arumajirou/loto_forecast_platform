from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "tools" / "evaluation" / "taj21_smoke_verify.py"
LAUNCHER_PATH = ROOT / "tools" / "taj21.sh"


def load_verifier():
    spec = importlib.util.spec_from_file_location("taj21_smoke_verify", VERIFIER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture(root: Path, *, expose_actuals: bool = False) -> None:
    candidates = [
        "baseline:random",
        "baseline:fixed",
        "baseline:mean",
        "baseline:median",
        "baseline:last",
        "baseline:frequency",
        "baseline:statistical_ar1",
        "logistic",
        "pp-multinomial-dglm",
    ]
    results = []
    for candidate_id in candidates:
        if candidate_id.startswith("baseline:"):
            source = "baseline"
            metadata = {"route": "mandatory_baseline"}
        elif candidate_id == "logistic":
            source = "catalog"
            metadata = {"route": "slot_conditioned_candidate"}
        else:
            source = "probabilistic"
            metadata = {
                "route": "probabilistic_primary_native_development_oof",
                "target_actual_present_in_fit_bundle": False,
                "target_actual_read": False,
            }

        safe_id = candidate_id.replace("/", "_").replace(":", "_")
        lock = root / "prediction_locks" / "numbers3" / safe_id / "seed-42.json"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock_payload = {
            "schema_version": "prediction-lock-v1",
            "game": "numbers3",
            "candidate_id": candidate_id,
            "seed": 42,
            "actuals_known": expose_actuals and candidate_id == "pp-multinomial-dglm",
            "predictions": [{"fold_id": 0, "draw_index": 12, "prediction": [1, 2, 3]}],
        }
        lock.write_text(json.dumps(lock_payload) + "\n", encoding="utf-8")
        results.append(
            {
                "game": "numbers3",
                "candidate_id": candidate_id,
                "source": source,
                "status": "SUCCEEDED",
                "seed_results": [
                    {
                        "seed": 42,
                        "prediction_lock": {
                            "path": str(lock),
                            "sha256": _sha256(lock),
                        },
                        "runtime_samples": [{"metadata": metadata}],
                    }
                ],
            }
        )

    summary = {
        "status": "SUCCEEDED",
        "matrix_complete": True,
        "games": ["numbers3"],
        "seeds": [42],
        "catalog_models": 2,
        "expected_model_game_pairs": 2,
        "observed_model_game_pairs": 2,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "results": results,
    }
    (root / "campaign_summary.json").write_text(
        json.dumps(summary) + "\n", encoding="utf-8"
    )
    artifacts = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [
        f"{_sha256(path)}  {path.relative_to(root).as_posix()}" for path in artifacts
    ]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_launcher_exposes_one_command_representative_smoke() -> None:
    source = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "{preflight|smoke}" in source
    assert "uv run --frozen python" in source
    assert "--games numbers3" in source
    assert "--models logistic,pp-multinomial-dglm" in source
    assert "--seeds 42" in source
    assert "--folds 1" in source
    assert "--test-size 1" in source
    assert "--holdout-size 0" in source
    assert "taj21_smoke_verify.py" in source


def test_smoke_verifier_accepts_exact_route_and_seal_evidence(tmp_path: Path) -> None:
    verifier = load_verifier()
    root = tmp_path / "smoke"
    root.mkdir()
    _write_fixture(root)

    result = verifier.verify_smoke(root)

    assert result["baseline_succeeded"] == 7
    assert result["broad_status"] == "SUCCEEDED"
    assert result["probabilistic_status"] == "SUCCEEDED"
    assert result["prediction_locks_verified"] == 9
    assert result["checksummed_artifacts_verified"] == 10


def test_smoke_verifier_rejects_target_actual_exposure(tmp_path: Path) -> None:
    verifier = load_verifier()
    root = tmp_path / "smoke"
    root.mkdir()
    _write_fixture(root, expose_actuals=True)

    with pytest.raises(ValueError, match="prediction lock exposes actuals"):
        verifier.verify_smoke(root)
