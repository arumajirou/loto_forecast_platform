from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.protocol import (
    DatasetItem,
    DeviceRequest,
    EnvironmentLane,
    GluonTSProviderRequest,
    GluonTSProviderResponse,
    PredictionRow,
    ProviderOperation,
    ProviderStatus,
    ResourcePolicy,
    protocol_schema_sha256,
)


def _dataset_item() -> DatasetItem:
    return DatasetItem(item_id="position-1", start="2000-01-01", target=[1.0, 2.0])


def test_provider_operation_contract_contains_all_p2_operations() -> None:
    assert {operation.value for operation in ProviderOperation} == {
        "fit_predict",
        "load_predict",
        "evaluate",
        "backtest",
        "model_discovery",
        "distribution_discovery",
        "runtime_certify",
    }


def test_fit_predict_contract_defaults_are_reproducible() -> None:
    request = GluonTSProviderRequest(
        request_id="request-1",
        run_id="run-1",
        lane=EnvironmentLane.COMPAT,
        operation=ProviderOperation.FIT_PREDICT,
        model_class="DeepAREstimator",
        dataset=[_dataset_item()],
    )

    assert request.seed == 1
    assert request.prediction_length == 1
    assert request.resource_policy.outer_workers == 8
    assert request.resource_policy.max_gpu_jobs == 1
    assert len(protocol_schema_sha256()) == 64
    assert protocol_schema_sha256() == protocol_schema_sha256()


@pytest.mark.parametrize(
    "operation",
    [
        ProviderOperation.FIT_PREDICT,
        ProviderOperation.EVALUATE,
        ProviderOperation.BACKTEST,
    ],
)
def test_data_operations_reject_empty_dataset(operation: ProviderOperation) -> None:
    with pytest.raises(ValidationError, match=f"{operation.value} requires"):
        GluonTSProviderRequest(
            request_id="request-1",
            run_id="run-1",
            lane=EnvironmentLane.COMPAT,
            operation=operation,
            model_class="DeepAREstimator",
        )


def test_cuda_request_rejects_disabled_gpu_queue() -> None:
    with pytest.raises(ValidationError, match="max_gpu_jobs"):
        GluonTSProviderRequest(
            request_id="request-1",
            run_id="run-1",
            lane=EnvironmentLane.LATEST,
            operation=ProviderOperation.FIT_PREDICT,
            model_class="DeepAREstimator",
            device=DeviceRequest.CUDA,
            dataset=[_dataset_item()],
            resource_policy=ResourcePolicy(outer_workers=8, max_gpu_jobs=0),
        )


def test_resource_policy_rejects_gpu_jobs_above_outer_workers() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        ResourcePolicy(outer_workers=1, max_gpu_jobs=2)


def test_dataset_and_predictions_reject_non_finite_values() -> None:
    with pytest.raises(ValidationError, match="finite"):
        DatasetItem(item_id="position-1", start="2000-01-01", target=[1.0, math.inf])

    with pytest.raises(ValidationError, match="finite"):
        PredictionRow(item_id="position-1", horizon=1, mean=math.nan)


def test_response_status_is_fail_closed() -> None:
    with pytest.raises(ValidationError, match="FAILED responses"):
        GluonTSProviderResponse(
            request_id="request-1",
            run_id="run-1",
            lane=EnvironmentLane.COMPAT,
            status=ProviderStatus.FAILED,
        )

    response = GluonTSProviderResponse(
        request_id="request-1",
        run_id="run-1",
        lane=EnvironmentLane.COMPAT,
        status=ProviderStatus.VERIFIED,
        predictions=[PredictionRow(item_id="position-1", horizon=1, mean=2.0)],
    )
    assert response.status is ProviderStatus.VERIFIED
