from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

MODULE = Path(__file__).parents[2] / "scripts/analysis/probability_quality.py"
SPEC = importlib.util.spec_from_file_location(
    "probability_quality_under_test",
    MODULE,
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_near_constant_probabilities_are_rejected():
    values = np.full(37, 1.1587451664705e-6)
    with pytest.raises(RuntimeError, match="near-constant"):
        mod.require_candidate_probability_quality(
            values,
            model_id="lightgbm-classifier",
        )


def test_nonconstant_probabilities_pass():
    values = np.linspace(0.01, 0.5, 37)
    report = mod.require_candidate_probability_quality(
        values,
        model_id="model",
    )
    assert not report.near_constant
    assert report.valid_probability_range
