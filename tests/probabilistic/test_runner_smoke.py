from __future__ import annotations

from pathlib import Path

from loto.probabilistic.config import load_run_config
from loto.probabilistic.runner import run_probabilistic


def test_small_runner_writes_transactional_artifacts(tmp_path: Path) -> None:
    config = load_run_config("configs/probabilistic/smoke.yaml").model_copy(
        update={
            "output": str(tmp_path),
            "models": [
                "pp-static-dirichlet-categorical",
                "pp-hierarchical-dirichlet-digits",
                "pp-bayesian-tcn",
                "pp-poisson-candidate-count",
                "pp-posterior-utility-hit1-mse",
            ],
            "test_size": 2,
            "posterior_draws": 32,
            "synthetic_rows": 90,
            "min_train_size": 60,
        }
    )
    result = run_probabilistic(config)
    assert result["status"] == "PASS"
    assert result["status_counts"] == {"PASS": 5}
    run_dir = Path(result["run_dir"])
    assert (run_dir / "results.json").is_file()
    assert (run_dir / "SHA256SUMS.json").is_file()
    assert list((run_dir / "comparison").glob("leaderboard-*.csv"))
