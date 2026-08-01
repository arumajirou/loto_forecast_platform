from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

MODULE = Path(__file__).parents[2] / "scripts/analysis/audit_candidate_feature_causality.py"
SPEC = importlib.util.spec_from_file_location("audit_candidate_feature_causality", MODULE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def _synthetic_frame(draws: int = 120, candidates: int = 37) -> pd.DataFrame:
    rows = []
    history = np.zeros((draws, candidates), dtype=float)

    for draw_index in range(draws):
        selected = [(draw_index + offset * 5) % candidates for offset in range(7)]
        history[draw_index, selected] = 1.0

    for draw_index in range(draws):
        for candidate_index in range(candidates):
            row = {
                "draw_no": draw_index + 1,
                "candidate_number": candidate_index + 1,
                "selected": history[draw_index, candidate_index],
            }
            for window in mod.WINDOWS:
                start = max(0, draw_index - window)
                prior = history[start:draw_index, candidate_index]
                row[f"freq_w{window}"] = float(prior.mean()) if len(prior) else 0.0
            rows.append(row)
    return pd.DataFrame(rows)


def test_strict_prior_rate_passes():
    report = mod.audit_frame(_synthetic_frame())
    assert report["causality_pass"] is True
    assert all(item["rate_match_rate"] == 1.0 for item in report["features"])


def test_current_draw_injection_fails():
    frame = _synthetic_frame()
    frame["freq_w5"] = frame["selected"]
    report = mod.audit_frame(frame)
    assert report["causality_pass"] is False
