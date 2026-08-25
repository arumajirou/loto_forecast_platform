from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.forecast_mcp.contracts import ForecastToolRequest
from loto.forecast_mcp.service import ForecastMcpService


def test_llm_cannot_override_operator_residency_policy() -> None:
    with pytest.raises(ValidationError):
        ForecastToolRequest.model_validate(
            {
                "game": "numbers3",
                "model": "moirai2",
                "horizon": 1,
                "device": "cuda",
                "scope": "development",
                "residency_mode": "coexist",
            }
        )


def test_mode_aware_supervisor_validation_accepts_handoff() -> None:
    selected = ForecastMcpService._validate_supervisor_result(
        {
            "status": "PASS",
            "qwen_initially_running": True,
            "qwen_stopped": True,
            "qwen_restored": True,
            "gate_reopened": True,
            "gpu_residency": {
                "selected_mode": "handoff",
                "llm_continuity_verified": False,
            },
        }
    )
    assert selected == "handoff"


def test_mode_aware_supervisor_validation_accepts_coexist() -> None:
    selected = ForecastMcpService._validate_supervisor_result(
        {
            "status": "PASS",
            "qwen_initially_running": True,
            "qwen_stopped": False,
            "qwen_restored": False,
            "gate_reopened": True,
            "gpu_residency": {
                "selected_mode": "coexist",
                "llm_continuity_verified": True,
            },
        }
    )
    assert selected == "coexist"


def test_coexist_without_continuity_evidence_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="continuity"):
        ForecastMcpService._validate_supervisor_result(
            {
                "status": "PASS",
                "qwen_initially_running": True,
                "qwen_stopped": False,
                "qwen_restored": False,
                "gate_reopened": True,
                "gpu_residency": {
                    "selected_mode": "coexist",
                    "llm_continuity_verified": False,
                },
            }
        )
