from __future__ import annotations

import json
from pathlib import Path

from loto.probabilistic.config import load_run_config
from loto.probabilistic.runner import run_probabilistic


def test_builtin_primary_native_path_writes_native_metadata(tmp_path: Path) -> None:
    config = load_run_config("configs/probabilistic/native_smoke.yaml").model_copy(
        update={
            "run_id": "native-builtin-contract",
            "output": str(tmp_path),
            "games": ["numbers3"],
            "models": ["pp-static-dirichlet-categorical"],
            "test_size": 1,
            "synthetic_rows": 80,
            "min_train_size": 50,
            "native_draws": 16,
        }
    )
    result = run_probabilistic(config)
    assert result["status"] == "PASS"
    assert result["status_counts"] == {"PASS": 1}
    run_dir = Path(result["run_dir"])
    metadata_files = list(run_dir.glob("models/*/posterior_metadata.json"))
    assert len(metadata_files) == 1
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["backend"] == "builtin"
    assert metadata["metadata"]["native_analytic"] is True
    assert metadata["metadata"]["native_graph_id"] == "static_dirichlet_categorical"
