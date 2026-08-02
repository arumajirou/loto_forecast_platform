from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.research_closure.core import (
    create_closure_package,
    create_shadow_lock,
    verify_sha256sums,
)


def synthetic_dataset(path: Path, rows: int = 900) -> Path:
    rng = np.random.default_rng(20260802)
    frame = pd.DataFrame(
        {
            "ds": pd.date_range("2020-01-01", periods=rows, freq="D"),
            "y": rng.integers(0, 10, size=rows),
        }
    )
    frame.to_csv(path, index=False)
    return path


def stage(artifact_root: Path, name: str, summary: dict) -> None:
    run = artifact_root / f"{name}-20260802-000000"
    run.mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps({"status": "PASS", **summary}), encoding="utf-8")


def test_closure_and_verify(tmp_path: Path) -> None:
    data = synthetic_dataset(tmp_path / "numbers3_n1.csv")
    artifacts = tmp_path / "artifacts"
    stage(
        artifacts, "stage-f0c-final-rolling-audit", {"best_mean_hit": 0.3132, "decision": "CLOSE"}
    )
    stage(
        artifacts,
        "stage-f1a-numpyro-categorical",
        {"top_method": "numpyro", "top_hit_within_1": 0.302},
    )
    stage(
        artifacts, "stage-f1b-dynamic-categorical", {"dynamic_hit": 0.288, "continue_to_f1c": False}
    )
    stage(
        artifacts,
        "stage-f2a-ordinal-catboost",
        {"top_method": "multinomial", "top_hit_within_1": 0.34},
    )
    stage(
        artifacts,
        "stage-f2b-repeated-logistic",
        {"best_method": "multinomial", "best_mean_hit": 0.30, "decision": "REJECT"},
    )
    output = tmp_path / "release"
    result = create_closure_package(tmp_path, artifacts, data, output)
    assert result.production_model is None
    assert (output / "documents" / "VERIFICATION_REPORT.md").is_file()
    assert verify_sha256sums(output) == []


def test_shadow_lock(tmp_path: Path) -> None:
    data = synthetic_dataset(tmp_path / "numbers3_n1.csv")
    output = tmp_path / "locks"
    result = create_shadow_lock(tmp_path, data, output, "2030-01-01")
    assert len(result.predictions) == 4
    lock = Path(result.lock_file)
    payload = json.loads(lock.read_text(encoding="utf-8"))
    assert payload["actual"] is None
    assert payload["status"] == "LOCKED_BEFORE_ACTUAL"
    assert lock.with_suffix(lock.suffix + ".sha256").is_file()
