from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.p6_contract import (
    FIT_CHECKS,
    FailureCategory,
    P6CheckState,
    P6Operation,
    P6ProviderRequest,
    P6StageEvidence,
    P6Status,
)


def test_fit_request_requires_one_dataset_item() -> None:
    with pytest.raises(ValidationError):
        P6ProviderRequest(
            request_id="r",
            run_id="run",
            lane="compat",
            operation=P6Operation.FIT_SERIALIZE,
            model_class="DeepAREstimator",
            artifact_dir="/tmp/predictor",
        )


def test_verified_stage_requires_every_check_pass() -> None:
    checks = {name: P6CheckState.PASS for name in FIT_CHECKS}
    with pytest.raises(ValidationError):
        P6StageEvidence(
            lane="compat",
            operation=P6Operation.FIT_SERIALIZE,
            model_class="DeepAREstimator",
            distribution_output="StudentTOutput",
            status=P6Status.VERIFIED,
            process_id=1,
            prediction_length=1,
            expected_shape=[1],
            observed_shape=[1],
            prediction_values=[1.0],
            observed_devices=["cpu"],
            checks=checks,
        )


def test_nonverified_stage_requires_failure_classification() -> None:
    with pytest.raises(ValidationError):
        P6StageEvidence(
            lane="compat",
            operation=P6Operation.FIT_SERIALIZE,
            model_class="DeepAREstimator",
            distribution_output="StudentTOutput",
            status=P6Status.BLOCKED,
            process_id=1,
            prediction_length=1,
            expected_shape=[1],
            checks={name: P6CheckState.NOT_RUN for name in FIT_CHECKS},
            errors=["blocked"],
        )
    evidence = P6StageEvidence(
        lane="compat",
        operation=P6Operation.FIT_SERIALIZE,
        model_class="DeepAREstimator",
        distribution_output="StudentTOutput",
        status=P6Status.BLOCKED,
        process_id=1,
        prediction_length=1,
        expected_shape=[1],
        failure_category=FailureCategory.VERSION_MISMATCH,
        checks={name: P6CheckState.NOT_RUN for name in FIT_CHECKS},
        errors=["blocked"],
    )
    assert evidence.failure_category is FailureCategory.VERSION_MISMATCH
