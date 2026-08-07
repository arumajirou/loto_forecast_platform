from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from loto.adapters.timer_s1.contracts import (
    CANONICAL_REPO,
    QUANTILE_KEYS,
    ChronologyEvidence,
    HistoryRow,
    ProviderStatus,
    TimerS1Request,
    TimerS1Response,
)


def history(position_count: int = 7, rows: int = 2) -> tuple[HistoryRow, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        HistoryRow(
            timestamp=start + timedelta(days=index),
            values=tuple(float(position + index) for position in range(position_count)),
        )
        for index in range(rows)
    )


def request_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "run_id": "timer-s1-test",
        "operation": "predict",
        "model_id": "timer-s1",
        "model_repo": CANONICAL_REPO,
        "package_version": "UNVERIFIED",
        "source_revision": "UNPINNED",
        "model_revision": "UNPINNED",
        "config_sha256": "UNPINNED",
        "weight_sha256": "UNPINNED",
        "weight_manifest_sha256": "UNPINNED",
        "license": "Apache-2.0",
        "game": "loto7",
        "target_layout": "position_univariate",
        "batch_semantics": "independent_series",
        "joint_multivariate": False,
        "timeline_mode": "draw-sequence",
        "context_length": 2,
        "prediction_length": 1,
        "seed": 1,
        "requested_device": "cpu",
        "history": [row.model_dump(mode="json") for row in history()],
        "past_covariates": None,
        "known_future_covariates": None,
        "snapshot_path": None,
        "manifest_path": None,
        "remote_code_review_path": None,
    }
    payload.update(overrides)
    return payload


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TimerS1Request.model_validate(request_payload(unknown=True))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_id", "timer"),
        ("model_repo", "thuml/Timer-S1"),
        ("joint_multivariate", True),
        ("past_covariates", []),
        ("known_future_covariates", []),
    ],
)
def test_invalid_identity_or_unsupported_arguments_are_rejected(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        TimerS1Request.model_validate(request_payload(**{field: value}))


@pytest.mark.parametrize("prediction_length", [1, 2, 5])
def test_contract_accepts_formal_horizons(prediction_length: int) -> None:
    request = TimerS1Request.model_validate(
        request_payload(prediction_length=prediction_length)
    )
    assert request.prediction_length == prediction_length


def test_future_actual_is_rejected() -> None:
    rows = [row.model_dump(mode="json") for row in history()]
    rows[-1]["future_actual"] = True
    with pytest.raises(ValidationError):
        TimerS1Request.model_validate(request_payload(history=rows))


def test_non_finite_history_is_rejected() -> None:
    rows = [row.model_dump(mode="json") for row in history()]
    rows[-1]["values"][0] = float("nan")
    with pytest.raises(ValidationError):
        TimerS1Request.model_validate(request_payload(history=rows))


def test_success_response_requires_q05_point_identity() -> None:
    quantiles = {
        key: ((float(index),),)
        for index, key in enumerate(QUANTILE_KEYS, start=1)
    }
    chronology = ChronologyEvidence(
        row_count=2,
        first_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        last_timestamp=datetime(2026, 1, 2, tzinfo=UTC),
        strictly_increasing=True,
        duplicate_timestamps=0,
        calendar_mapping_sha256="a" * 64,
    )
    with pytest.raises(ValidationError):
        TimerS1Response(
            run_id="response-test",
            status=ProviderStatus.VERIFIED_CPU,
            model_id="timer-s1",
            model_repo=CANONICAL_REPO,
            package_version="1",
            source_revision="a" * 40,
            model_revision="b" * 40,
            config_sha256="c" * 64,
            weight_sha256="d" * 64,
            weight_manifest_sha256="e" * 64,
            game="loto7",
            target_layout="position_univariate",
            timeline_mode="draw-sequence",
            context_length=2,
            prediction_length=1,
            seed=1,
            requested_device="cpu",
            effective_device="cpu",
            cpu_fallback=False,
            input_shape=(1, 2),
            native_output_shape=(1, 9, 1),
            output_shape=(1, 1),
            point_forecast=((999.0,),),
            quantiles=quantiles,
            samples=None,
            chronology_evidence=chronology,
            runtime_pid=1,
        )


def test_cpu_fallback_cannot_produce_verified_gpu() -> None:
    quantiles = {
        key: ((float(index),),)
        for index, key in enumerate(QUANTILE_KEYS, start=1)
    }
    chronology = ChronologyEvidence(
        row_count=2,
        first_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        last_timestamp=datetime(2026, 1, 2, tzinfo=UTC),
        strictly_increasing=True,
        duplicate_timestamps=0,
        calendar_mapping_sha256="a" * 64,
    )
    with pytest.raises(ValidationError):
        TimerS1Response(
            run_id="gpu-test",
            status=ProviderStatus.VERIFIED_GPU,
            model_id="timer-s1",
            model_repo=CANONICAL_REPO,
            package_version="1",
            source_revision="a" * 40,
            model_revision="b" * 40,
            config_sha256="c" * 64,
            weight_sha256="d" * 64,
            weight_manifest_sha256="e" * 64,
            game="loto7",
            target_layout="position_univariate",
            timeline_mode="draw-sequence",
            context_length=2,
            prediction_length=1,
            seed=1,
            requested_device="cuda",
            effective_device="cpu",
            cpu_fallback=True,
            input_shape=(1, 2),
            native_output_shape=(1, 9, 1),
            output_shape=(1, 1),
            point_forecast=quantiles["q0.5"],
            quantiles=quantiles,
            samples=None,
            chronology_evidence=chronology,
            runtime_pid=1,
            gpu_uuid="GPU-test",
            gpu_process_vram_peak_bytes=1,
        )


def valid_response_payload(**overrides: object) -> dict[str, object]:
    quantiles = {
        key: tuple((float(level_index),) for _ in range(7))
        for level_index, key in enumerate(QUANTILE_KEYS, start=1)
    }
    chronology = ChronologyEvidence(
        row_count=2,
        first_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        last_timestamp=datetime(2026, 1, 2, tzinfo=UTC),
        strictly_increasing=True,
        duplicate_timestamps=0,
        calendar_mapping_sha256="a" * 64,
    )
    payload: dict[str, object] = {
        "run_id": "verified-response",
        "status": "VERIFIED_CPU",
        "model_id": "timer-s1",
        "model_repo": CANONICAL_REPO,
        "package_version": "1",
        "source_revision": "a" * 40,
        "model_revision": "b" * 40,
        "config_sha256": "c" * 64,
        "weight_sha256": "d" * 64,
        "weight_manifest_sha256": "e" * 64,
        "game": "loto7",
        "target_layout": "position_univariate",
        "timeline_mode": "draw-sequence",
        "context_length": 2,
        "prediction_length": 1,
        "seed": 1,
        "requested_device": "cpu",
        "effective_device": "cpu",
        "cpu_fallback": False,
        "input_shape": (7, 2),
        "native_output_shape": (7, 9, 1),
        "output_shape": (7, 1),
        "point_forecast": quantiles["q0.5"],
        "quantiles": quantiles,
        "samples": None,
        "chronology_evidence": chronology,
        "runtime_pid": 1,
    }
    payload.update(overrides)
    return payload


def test_success_response_accepts_quantile_mapping_independent_of_key_order() -> None:
    payload = valid_response_payload()
    quantiles = payload["quantiles"]
    assert isinstance(quantiles, dict)
    payload["quantiles"] = dict(reversed(tuple(quantiles.items())))
    response = TimerS1Response.model_validate(payload)
    assert response.status is ProviderStatus.VERIFIED_CPU


def test_success_response_rejects_non_verified_status() -> None:
    with pytest.raises(ValidationError):
        TimerS1Response.model_validate(valid_response_payload(status="FAILED"))


def test_success_response_rejects_non_finite_quantile() -> None:
    payload = valid_response_payload()
    quantiles = dict(payload["quantiles"])
    rows = list(quantiles["q0.9"])
    rows[0] = (float("nan"),)
    quantiles["q0.9"] = tuple(rows)
    payload["quantiles"] = quantiles
    with pytest.raises(ValidationError, match="finite"):
        TimerS1Response.model_validate(payload)


def test_success_response_rejects_quantile_crossing() -> None:
    payload = valid_response_payload()
    quantiles = dict(payload["quantiles"])
    rows = list(quantiles["q0.9"])
    rows[0] = (0.0,)
    quantiles["q0.9"] = tuple(rows)
    payload["quantiles"] = quantiles
    with pytest.raises(ValidationError, match="monotone"):
        TimerS1Response.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_shape", (1, 2)),
        ("native_output_shape", (7, 8, 1)),
        ("output_shape", (1, 1)),
    ],
)
def test_success_response_rejects_shape_claims_not_bound_to_game_geometry(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError, match="shape"):
        TimerS1Response.model_validate(valid_response_payload(**{field: value}))


def test_success_response_rejects_chronology_row_count_mismatch() -> None:
    chronology = ChronologyEvidence(
        row_count=3,
        first_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        last_timestamp=datetime(2026, 1, 3, tzinfo=UTC),
        strictly_increasing=True,
        duplicate_timestamps=0,
        calendar_mapping_sha256="a" * 64,
    )
    with pytest.raises(ValidationError, match="row_count"):
        TimerS1Response.model_validate(
            valid_response_payload(chronology_evidence=chronology)
        )


def test_verified_cpu_rejects_gpu_evidence() -> None:
    with pytest.raises(ValidationError, match="GPU process evidence"):
        TimerS1Response.model_validate(
            valid_response_payload(
                gpu_uuid="GPU-test",
                gpu_process_vram_before_bytes=0,
                gpu_process_vram_peak_bytes=1,
                gpu_process_vram_after_bytes=0,
            )
        )


def test_success_response_rejects_unsafe_artifact_path() -> None:
    with pytest.raises(ValidationError, match="run directory"):
        TimerS1Response.model_validate(
            valid_response_payload(artifact_paths=("../escape.json",))
        )


@pytest.mark.parametrize("package_version", ["", " ", "UNVERIFIED", "UNPINNED"])
def test_verified_response_requires_concrete_package_version(
    package_version: str,
) -> None:
    with pytest.raises(ValidationError, match="package_version"):
        TimerS1Response.model_validate(
            valid_response_payload(package_version=package_version)
        )
