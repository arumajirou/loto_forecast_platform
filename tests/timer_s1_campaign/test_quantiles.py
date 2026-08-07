from __future__ import annotations

import pytest

from loto.adapters.timer_s1.contracts import QUANTILE_KEYS
from loto.timer_s1_campaign.quantiles import normalize_native_quantiles


def native_output() -> list[list[list[float]]]:
    return [[[float(level), float(level + 1)] for level in range(9)]]


def test_exact_nine_quantiles_and_q05_point() -> None:
    quantiles, point, shape = normalize_native_quantiles(native_output(), 2)
    assert tuple(quantiles) == QUANTILE_KEYS
    assert point == quantiles["q0.5"]
    assert shape == (1, 9, 2)


def test_quantile_crossing_is_rejected() -> None:
    output = native_output()
    output[0][5][0] = -1.0
    with pytest.raises(ValueError, match="cross"):
        normalize_native_quantiles(output, 2)


def test_wrong_quantile_inventory_is_rejected() -> None:
    with pytest.raises(ValueError, match="nine quantiles"):
        normalize_native_quantiles([native_output()[0][:-1]], 2)
