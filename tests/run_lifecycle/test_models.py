from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from loto.run_lifecycle import (
    CanonicalJsonObject,
    HashBinding,
    RunCommand,
    RunCommandType,
    RunPhase,
)


def valid_command_payload() -> dict[str, object]:
    return {
        "command_id": "cmd-1",
        "run_id": "run-1",
        "command_type": RunCommandType.START,
        "phase": RunPhase.PLAN,
        "expected_revision": 0,
        "issued_at": datetime(2026, 8, 6, tzinfo=UTC),
        "actor_id": "operator-1",
    }


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RunCommand.model_validate({**valid_command_payload(), "unknown": "no"})


def test_implicit_coercion_and_bool_int_confusion_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RunCommand.model_validate({**valid_command_payload(), "expected_revision": "0"})
    with pytest.raises(ValidationError):
        RunCommand.model_validate({**valid_command_payload(), "expected_revision": True})


def test_naive_and_non_utc_datetime_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RunCommand.model_validate({**valid_command_payload(), "issued_at": datetime(2026, 8, 6)})


def test_sha256_and_identifier_are_fail_closed() -> None:
    with pytest.raises(ValidationError):
        HashBinding(name="../unsafe", sha256="a" * 64)
    with pytest.raises(ValidationError):
        HashBinding(name="safe", sha256="A" * 64)
    with pytest.raises(ValidationError):
        HashBinding(name="safe", sha256="a" * 63)


def test_canonical_json_rejects_noncanonical_and_nonfinite_payloads() -> None:
    with pytest.raises(ValidationError):
        CanonicalJsonObject(text='{"b":2, "a":1}')
    with pytest.raises(ValidationError):
        CanonicalJsonObject(text='{"value":NaN}')
    value = CanonicalJsonObject.from_object({"b": 2, "a": 1})
    assert value.text == '{"a":1,"b":2}'


def test_frozen_models_and_immutable_defaults() -> None:
    command = RunCommand(**valid_command_payload())
    with pytest.raises(ValidationError):
        command.expected_revision = 2  # type: ignore[misc]
    assert command.subject_hashes == ()
    assert command.requested_output_names == ()
