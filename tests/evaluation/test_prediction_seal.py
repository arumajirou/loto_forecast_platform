from __future__ import annotations

import json

import pytest

from loto.evaluation.prediction_seal import (
    seal_prediction_record,
    verify_sealed_prediction,
)


def test_prediction_is_persisted_and_sealed_before_actual(
    tmp_path,
) -> None:
    sealed = seal_prediction_record(
        tmp_path,
        stem="candidate-seed42",
        record={
            "schema_version": "test-prediction.v1",
            "prediction": [1.25, 2.5, 3.75],
            "target_actual_included": False,
        },
    )

    verify_sealed_prediction(sealed)

    payload = json.loads(sealed.seal_path.read_text(encoding="utf-8"))

    assert payload["target_actual_read"] is False


def test_mutated_prediction_fails_seal_verification(
    tmp_path,
) -> None:
    sealed = seal_prediction_record(
        tmp_path,
        stem="candidate-seed42",
        record={
            "prediction": [1.0],
            "target_actual_included": False,
        },
    )

    sealed.record_path.write_text(
        '{"prediction":[2.0]}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        verify_sealed_prediction(sealed)


def test_prediction_artifact_cannot_be_overwritten(
    tmp_path,
) -> None:
    record = {
        "prediction": [1.0],
        "target_actual_included": False,
    }

    seal_prediction_record(
        tmp_path,
        stem="candidate",
        record=record,
    )

    with pytest.raises(FileExistsError):
        seal_prediction_record(
            tmp_path,
            stem="candidate",
            record=record,
        )
