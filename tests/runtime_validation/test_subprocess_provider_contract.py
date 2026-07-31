from __future__ import annotations

import numpy as np
import pytest

from loto.models.providers.subprocess import (
    SubprocessProviderContractError,
    validate_provider_request,
    validate_provider_response,
)


def valid_request() -> dict:
    return {
        "schema_version": 1,
        "model_id": "granite-ttm",
        "repo_id": "ibm-granite/granite-timeseries-ttm-r2",
        "local_files_only": True,
        "device": "cpu",
        "dtype": "float32",
        "history": [{"n1": 1, "n2": 2, "n3": 3, "n4": 4, "n5": 5, "n6": 6, "n7": 7}],
        "prediction_length": 1,
    }


def valid_response(tmp_path) -> dict:
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "predictions": [1, 2, 3, 4, 5, 6, 7],
        "shape": [7],
        "finite": True,
        "properties": {
            "license": "apache-2.0",
            "weight_sha256": {"model.safetensors": "abc"},
            "config_sha256": "def",
        },
        "gpu_evidence": {"device": "cpu", "vram_peak_bytes": 0},
        "artifact_reference": {"snapshot_path": str(tmp_path)},
    }


def test_subprocess_provider_request_validation():
    request = valid_request()
    validate_provider_request(request)
    del request["repo_id"]
    with pytest.raises(SubprocessProviderContractError, match="missing request keys"):
        validate_provider_request(request)


def test_subprocess_provider_response_validation(tmp_path):
    predictions = validate_provider_response(valid_response(tmp_path))
    assert predictions.shape == (7,)


def test_subprocess_provider_rejects_invalid_shape(tmp_path):
    response = valid_response(tmp_path)
    response["predictions"] = [1, 2]
    with pytest.raises(SubprocessProviderContractError, match="prediction shape mismatch"):
        validate_provider_response(response)


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_subprocess_provider_rejects_nan_inf(tmp_path, bad):
    response = valid_response(tmp_path)
    response["predictions"][0] = bad
    with pytest.raises(SubprocessProviderContractError, match="NaN or Inf"):
        validate_provider_response(response)


def test_subprocess_provider_rejects_missing_snapshot(tmp_path):
    response = valid_response(tmp_path)
    response["artifact_reference"]["snapshot_path"] = str(tmp_path / "missing")
    with pytest.raises(SubprocessProviderContractError, match="snapshot_path does not exist"):
        validate_provider_response(response)


def test_subprocess_provider_rejects_partial_metadata(tmp_path):
    response = valid_response(tmp_path)
    response["properties"] = {}
    with pytest.raises(SubprocessProviderContractError, match="license metadata"):
        validate_provider_response(response)


def test_subprocess_provider_rejects_unknown_schema_version():
    request = valid_request()
    request["schema_version"] = 999
    with pytest.raises(SubprocessProviderContractError, match="unsupported schema_version"):
        validate_provider_request(request)


def test_subprocess_provider_requires_gpu_evidence(tmp_path):
    response = valid_response(tmp_path)
    response.pop("gpu_evidence")
    with pytest.raises(SubprocessProviderContractError, match="gpu_evidence"):
        validate_provider_response(response)


def test_subprocess_provider_error_status_maps_to_contract_error():
    with pytest.raises(SubprocessProviderContractError, match="timed out"):
        validate_provider_response({"status": "TIMEOUT", "message": "provider timed out"})
