from __future__ import annotations

from types import SimpleNamespace

import pytest

from loto.adapters.autogluon.search_spaces import (
    SearchSpaceDescriptorError,
    contains_search_space_descriptor,
    materialize_search_spaces,
    validate_search_space_descriptors,
)


class _Constructor:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, *args, **kwargs):
        return {"constructor": self.name, "args": args, "kwargs": kwargs}


SPACE = SimpleNamespace(
    Categorical=_Constructor("Categorical"),
    Int=_Constructor("Int"),
    Real=_Constructor("Real"),
)


def test_materializes_nested_json_safe_search_spaces() -> None:
    payload = {
        "SeasonalNaive": {
            "seasonal_period": {
                "__space__": "categorical",
                "choices": [1, 2],
            },
            "max_ts_length": {
                "__space__": "int",
                "lower": 10,
                "upper": 20,
                "default": 12,
            },
            "learning_rate": {
                "__space__": "real",
                "lower": 0.001,
                "upper": 0.1,
                "default": 0.01,
                "log": True,
            },
        }
    }
    validate_search_space_descriptors(payload)
    assert contains_search_space_descriptor(payload)
    materialized = materialize_search_spaces(payload, space_module=SPACE)
    model = materialized["SeasonalNaive"]
    assert model["seasonal_period"]["constructor"] == "Categorical"
    assert model["seasonal_period"]["args"] == (1, 2)
    assert model["max_ts_length"]["kwargs"]["default"] == 12
    assert model["learning_rate"]["kwargs"]["log"] is True


@pytest.mark.parametrize(
    "descriptor",
    [
        {"__space__": "unknown", "choices": [1, 2]},
        {"__space__": "categorical", "choices": [1]},
        {"__space__": "int", "lower": 2, "upper": 1},
        {"__space__": "real", "lower": 0.0, "upper": 1.0, "log": "yes"},
        {"__space__": "int", "lower": 1, "upper": 3, "extra": True},
    ],
)
def test_invalid_descriptors_fail_closed(descriptor) -> None:
    with pytest.raises(SearchSpaceDescriptorError):
        validate_search_space_descriptors({"Model": {"value": descriptor}})
