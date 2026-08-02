from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.research_closure.core import create_shadow_lock


def test_shadow_lock_is_true_future_and_idempotent(tmp_path: Path) -> None:
    rows = 900
    data = pd.DataFrame(
        {
            "ds": pd.date_range("2020-01-01", periods=rows, freq="D"),
            "y": [i % 10 for i in range(rows)],
        }
    )
    data_path = tmp_path / "data.parquet"
    data.to_parquet(data_path, index=False)
    target = "2022-06-20"
    result = create_shadow_lock(tmp_path, data_path, tmp_path / "locks", target)
    payload = json.loads(Path(result.lock_file).read_text())
    assert payload["schema_version"] == "1.1"
    assert payload["actual"] is None
    assert payload["models"]["tree_depth4"]["forecast_feature_ds"].startswith(target)
    assert payload["models"]["tree_depth4"]["training_cutoff_ds"] == str(data["ds"].max())
    assert payload["models"]["tree_depth4"]["model_state_sha256"]
    assert (tmp_path / "locks" / "CURRENT.json").exists()
    with pytest.raises(FileExistsError):
        create_shadow_lock(tmp_path, data_path, tmp_path / "locks", target)
