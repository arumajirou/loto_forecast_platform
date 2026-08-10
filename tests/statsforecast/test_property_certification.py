from __future__ import annotations

from types import SimpleNamespace

from loto.statsforecast.property_certification import (
    normalize_property,
    property_snapshot,
    property_snapshot_passes,
)


class DirectModel:
    def __init__(
        self,
        season_length: int,
    ) -> None:
        self.season_length = season_length


class FakeAutoRegressive:
    def __init__(
        self,
        *,
        order,
        fixed,
    ) -> None:
        self.order = order
        self.fixed = fixed


def test_normalize_property_converts_tuple() -> None:
    assert normalize_property((1, 0, 0)) == [1, 0, 0]


def test_direct_property_match() -> None:
    model = DirectModel(season_length=4)

    evidence = property_snapshot(
        "DirectModel",
        model,
        {"season_length": 4},
    )

    assert evidence["season_length"]["mode"] == "DIRECT"

    assert evidence["season_length"]["match"] is True

    assert property_snapshot_passes(evidence) is True


def test_direct_property_mismatch() -> None:
    model = DirectModel(season_length=5)

    evidence = property_snapshot(
        "DirectModel",
        model,
        {"season_length": 4},
    )

    assert evidence["season_length"]["match"] is False

    assert property_snapshot_passes(evidence) is False


def test_autoregressive_integer_lags_mapping() -> None:
    model = FakeAutoRegressive(
        order=(1, 0, 0),
        fixed=None,
    )

    evidence = property_snapshot(
        "AutoRegressive",
        model,
        {"lags": 1},
    )

    assert evidence["lags"]["mode"] == "DERIVED"
    assert evidence["lags"]["match"] is True


def test_autoregressive_sparse_lags_mapping() -> None:
    model = FakeAutoRegressive(
        order=(3, 0, 0),
        fixed={
            "ar1": float("nan"),
            "ar2": 0,
            "ar3": float("nan"),
        },
    )

    evidence = property_snapshot(
        "AutoRegressive",
        model,
        {"lags": [1, 3]},
    )

    assert evidence["lags"]["effective"] == {
        "order": [3, 0, 0],
        "fixed": {
            "ar1": "NaN",
            "ar2": 0,
            "ar3": "NaN",
        },
    }

    assert evidence["lags"]["match"] is True


def test_missing_direct_property_is_fail_visible() -> None:
    model = SimpleNamespace()

    evidence = property_snapshot(
        "DirectModel",
        model,
        {"season_length": 4},
    )

    assert evidence["season_length"]["mode"] == "MISSING_DIRECT_PROPERTY"

    assert property_snapshot_passes(evidence) is False
