from __future__ import annotations

import pandas as pd

from loto.observability.evidently_bridge import build_drift_summary


def test_evidently_bridge_degrades_cleanly_without_optional_dependency() -> None:
    result = build_drift_summary(pd.DataFrame({"x": [1, 2]}), pd.DataFrame({"x": [2, 3]}))
    assert result.rows_reference == 2
    assert result.rows_current == 2
