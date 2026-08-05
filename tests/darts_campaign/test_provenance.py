from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from loto.darts_campaign.provenance import build_run_provenance, hash_dataframe, hash_mapping


def test_provenance_hashes_are_stable_and_tamper_sensitive(tmp_path) -> None:
    frame = pd.DataFrame({"draw_no": [1, 2], "n1": [3, 4]})
    code = tmp_path / "model.py"
    code.write_text("VALUE = 1\n", encoding="utf-8")
    created = datetime(2026, 8, 5, 5, 0, tzinfo=UTC)
    kwargs = {
        "run_id": "run-1",
        "frame": frame,
        "config": {"seed": 1, "horizon": 1},
        "code_paths": [code],
        "git_commit": "0ab309f5ba2b80fe8d04168027f052e8f58c2b05",
        "model_id": "darts-ensemble",
        "model_revision": "darts-0.46.1",
        "seeds": (1, 7),
        "created_at_utc": created,
    }
    first = build_run_provenance(**kwargs)
    second = build_run_provenance(**kwargs)
    assert first == second

    changed = frame.copy(deep=True)
    changed.loc[1, "n1"] = 5
    assert hash_dataframe(changed) != first.data_sha256
    assert hash_mapping({"horizon": 2}) != first.config_sha256


def test_provenance_rejects_naive_time_and_single_seed(tmp_path) -> None:
    code = tmp_path / "model.py"
    code.write_text("VALUE = 1\n", encoding="utf-8")
    common = {
        "run_id": "run-1",
        "frame": pd.DataFrame({"draw_no": [1, 2]}),
        "config": {},
        "code_paths": [code],
        "git_commit": "0ab309f",
        "model_id": "model",
        "model_revision": "revision",
        "seeds": (1, 7),
    }
    with pytest.raises(ValueError, match="timezone-aware"):
        build_run_provenance(**common, created_at_utc=datetime(2026, 8, 5, 5, 0))
    with pytest.raises(ValueError, match="two unique seeds"):
        build_run_provenance(
            **{**common, "seeds": (1,)},
            created_at_utc=datetime(2026, 8, 5, 5, 0, tzinfo=UTC),
        )
