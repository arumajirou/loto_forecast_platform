from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.basicts_campaign.contracts import BasicTSProviderRequest


def _valid_request() -> dict[str, object]:
    return {
        "schema_version": "loto-basicts-provider-v1",
        "request_id": "contract-1",
        "operation": "validate_config",
        "artifact_dir": "artifacts/basicts/contract-1",
        "config": {
            "model": {
                "module": "loto.adapters.basicts.smoke_model",
                "name": "TinyLinearForecaster",
            },
            "optimizer": {"module": "torch.optim", "name": "Adam"},
            "lr_scheduler": None,
            "input_len": 8,
            "output_len": 1,
            "channels": 3,
            "seed": 1,
            "gpus": None,
            "eval_after_train": False,
            "test_interval": None,
            "deterministic": True,
        },
        "dataset": None,
    }


def test_request_rejects_unknown_keys() -> None:
    payload = _valid_request()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        BasicTSProviderRequest.model_validate(payload)


def test_request_rejects_holdout_auto_evaluation() -> None:
    payload = _valid_request()
    assert isinstance(payload["config"], dict)
    payload["config"]["eval_after_train"] = True
    with pytest.raises(ValidationError):
        BasicTSProviderRequest.model_validate(payload)


def test_request_rejects_parent_traversal() -> None:
    payload = _valid_request()
    payload["artifact_dir"] = "../unsafe"
    with pytest.raises(ValidationError):
        BasicTSProviderRequest.model_validate(payload)
