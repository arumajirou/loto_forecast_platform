from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from loto.data_access_ledger import (
    NON_CLAIMS,
    AccessEvent,
    AccessOperation,
    DataAccessLedger,
    DataRole,
    DatasetSlice,
)
from tests.data_access_ledger.conftest import ORIGIN, as_python, make_event, make_slice


def test_dataset_slice_rejects_unknown_field() -> None:
    payload = as_python(make_slice())
    payload["unknown"] = "forbidden"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DatasetSlice.model_validate(payload)


def test_strict_contract_rejects_bool_as_integer() -> None:
    payload = as_python(make_event(event_id="read", sequence_no=1, operation=AccessOperation.READ))
    payload["sequence_no"] = True
    with pytest.raises(ValidationError):
        AccessEvent.model_validate(payload)


def test_naive_datetime_is_rejected() -> None:
    payload = as_python(make_slice())
    payload["available_at"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        DatasetSlice.model_validate(payload)


def test_non_utc_offset_is_rejected() -> None:
    payload = as_python(make_slice())
    payload["forecast_origin"] = ORIGIN.astimezone().replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        DatasetSlice.model_validate(payload)


def test_uppercase_sha_is_rejected() -> None:
    payload = as_python(make_slice())
    payload["dataset_sha256"] = "A" * 64
    with pytest.raises(ValidationError):
        DatasetSlice.model_validate(payload)


def test_actual_flag_requires_actual_role() -> None:
    with pytest.raises(ValidationError, match="ACTUALS role"):
        make_slice(data_role=DataRole.TRAIN, contains_actuals=True)


def test_ledger_serializes_and_deserializes(valid_train_model_ledger: DataAccessLedger) -> None:
    serialized = valid_train_model_ledger.model_dump_json()
    restored = DataAccessLedger.model_validate_json(serialized)
    assert restored == valid_train_model_ledger


def test_non_claims_forbid_fixture_overclaim() -> None:
    assert any("fixture PASS" in statement for statement in NON_CLAIMS)
    assert any("real Train" in statement for statement in NON_CLAIMS)
