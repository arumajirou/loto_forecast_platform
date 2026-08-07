from __future__ import annotations

import pytest

from loto.darts_campaign.argument_validator import classify_arguments


class Model:
    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha


def test_argument_ledger_accepts_known_key() -> None:
    effective, ledger = classify_arguments(Model, {"alpha": 2.0})
    assert effective == {"alpha": 2.0}
    assert ledger[0].status == "ACCEPTED"


def test_argument_ledger_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown"):
        classify_arguments(Model, {"unknown": 1})
