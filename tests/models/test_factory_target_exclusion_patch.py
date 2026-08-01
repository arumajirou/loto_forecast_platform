from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE = Path(__file__).parents[2] / "scripts/maintenance/patch_factory_target_exclusion.py"
SPEC = importlib.util.spec_from_file_location(
    "patch_factory_under_test",
    MODULE,
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_patch_excludes_declared_target():
    source = """
class RuntimeModel:
    def fit_candidate(self, train, target_column="selected"):
        if target_column not in train:
            raise ValueError(target_column)
        self.feature_columns = numeric_feature_columns(
            train
        )
        X = train[self.feature_columns]
        y = train[target_column]
"""
    patched, changed = mod.patch_factory_text(source)
    assert changed
    assert "if column != target_column" in patched
    assert "target column leaked into features" in patched


def test_patch_handles_one_line_assignment():
    source = """
class RuntimeModel:
    def fit_candidate(self, train, target_column="selected"):
        self.feature_columns = numeric_feature_columns(train)
        X = train[self.feature_columns]
"""
    patched, changed = mod.patch_factory_text(source)
    assert changed
    compile(patched, "<patched>", "exec")


def test_patch_is_idempotent():
    source = """
class RuntimeModel:
    def fit_candidate(self, train, target_column="selected"):
        self.feature_columns = [
            column
            for column in numeric_feature_columns(train)
            if column != target_column
        ]
        if target_column in self.feature_columns:
            raise RuntimeError(
                f"target column leaked into features: {target_column}"
            )
        X = train[self.feature_columns]
"""
    patched, changed = mod.patch_factory_text(source)
    assert not changed
    assert patched == source


def test_candidate_prediction_rejects_missing_fitted_feature_column():
    import pandas as pd
    import pytest

    from loto.models.catalog import get_model_spec
    from loto.models.factory import RuntimeModel

    train = pd.DataFrame(
        {
            "candidate_number": [1, 2, 3, 4],
            "feature_a": [0.1, 0.2, 0.3, 0.4],
            "feature_b": [1.0, 0.0, 1.0, 0.0],
            "selected": [0, 1, 0, 1],
        }
    )

    runtime = RuntimeModel(
        get_model_spec("extra-trees"),
        {"n_estimators": 5},
        seed=42,
    ).fit_candidate(train)

    query = pd.DataFrame(
        {
            "candidate_number": [5, 6],
            "feature_a": [0.5, 0.6],
        }
    )

    with pytest.raises(
        ValueError,
        match="query is missing fitted feature columns: feature_b",
    ):
        runtime.predict_candidate(query)


def test_position_prediction_rejects_missing_fitted_feature_column():
    import numpy as np
    import pandas as pd
    import pytest

    from loto.models.catalog import get_model_spec
    from loto.models.factory import RuntimeModel

    train_x = pd.DataFrame(
        {
            "feature_a": [0.1, 0.2, 0.3, 0.4],
            "feature_b": [1.0, 0.0, 1.0, 0.0],
        }
    )
    train_y = np.array([1.0, 2.0, 3.0, 4.0])

    runtime = RuntimeModel(
        get_model_spec("ridge-position"),
        {},
        seed=42,
    ).fit_position(train_x, train_y)

    query = pd.DataFrame({"feature_a": [0.5]})

    with pytest.raises(
        ValueError,
        match="query is missing fitted feature columns: feature_b",
    ):
        runtime.predict_position(query)
