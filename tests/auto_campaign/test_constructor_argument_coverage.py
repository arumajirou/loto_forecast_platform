from __future__ import annotations

import pytest

from loto.auto_campaign.model_factory import _constructor_argument_decisions


class ExplicitConstructor:
    def __init__(self, h, config):
        self.h = h
        self.config = config


class VariadicConstructor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_constructor_argument_decisions_classify_every_key() -> None:
    effective, ledger = _constructor_argument_decisions(
        ExplicitConstructor,
        {
            "h": 1,
            "config": {},
            "alias": "candidate",
            "cpus": None,
            "gpus": None,
        },
        strict_keys=set(),
    )

    assert effective == {"h": 1, "config": {}}
    statuses = {row["argument"]: row["status"] for row in ledger}
    assert statuses == {
        "h": "ACCEPTED",
        "config": "ACCEPTED",
        "alias": "NOT_APPLICABLE",
        "cpus": "UNSUPPORTED_BY_VERSION",
        "gpus": "UNSUPPORTED_BY_VERSION",
    }
    assert not any(row["status"] == "DROPPED" for row in ledger)


def test_explicit_extra_argument_is_rejected_instead_of_dropped() -> None:
    with pytest.raises(ValueError, match="explicit arguments"):
        _constructor_argument_decisions(
            ExplicitConstructor,
            {"h": 1, "config": {}, "custom_flag": True},
            strict_keys={"custom_flag"},
        )


def test_variadic_constructor_accepts_all_arguments() -> None:
    effective, ledger = _constructor_argument_decisions(
        VariadicConstructor,
        {"h": 1, "custom_flag": True},
        strict_keys={"custom_flag"},
    )

    assert effective == {"h": 1, "custom_flag": True}
    assert {row["status"] for row in ledger} == {"ACCEPTED"}
