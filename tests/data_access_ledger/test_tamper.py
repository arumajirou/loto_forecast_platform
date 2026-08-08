from __future__ import annotations

import math

import pytest
from conftest import make_event, make_ledger

from loto.data_access_ledger import (
    AccessOperation,
    FindingCode,
    canonical_json_bytes,
    compute_ledger_sha256,
    validate_ledger,
)


def test_canonical_hash_ignores_dictionary_input_order() -> None:
    first = {"a": 1, "b": {"x": 2, "y": 3}}
    second = {"b": {"y": 3, "x": 2}, "a": 1}
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_event_order_changes_ledger_hash() -> None:
    first = make_event(event_id="first", sequence_no=1, operation=AccessOperation.READ)
    second = make_event(event_id="second", sequence_no=2, operation=AccessOperation.READ)
    ledger = make_ledger([first, second])
    reversed_ledger = ledger.model_copy(
        update={
            "events": [second, first],
            "first_event_at": second.occurred_at,
            "last_event_at": first.occurred_at,
        }
    )
    assert compute_ledger_sha256(ledger) != compute_ledger_sha256(reversed_ledger)


def test_ledger_tamper_is_detected(valid_train_model_ledger) -> None:
    changed_event = valid_train_model_ledger.events[0].model_copy(update={"notes": "tampered"})
    tampered = valid_train_model_ledger.model_copy(update={"events": [changed_event]})
    assert FindingCode.LEDGER_HASH_MISMATCH in {
        item.code for item in validate_ledger(tampered).findings
    }


def test_nan_and_infinity_are_rejected_by_canonicalization() -> None:
    with pytest.raises(ValueError, match="NaN and infinity"):
        canonical_json_bytes(math.nan)
    with pytest.raises(ValueError, match="NaN and infinity"):
        canonical_json_bytes(math.inf)


def test_set_and_bytes_are_rejected_by_canonicalization() -> None:
    with pytest.raises(TypeError, match="unsupported canonical JSON type"):
        canonical_json_bytes({"bad": {1, 2}})
    with pytest.raises(TypeError, match="unsupported canonical JSON type"):
        canonical_json_bytes({"bad": b"bytes"})
