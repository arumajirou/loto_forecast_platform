from __future__ import annotations

from loto.adapters.timer_s1.contracts import (
    ProviderStatus,
    TimerS1FailureResponse,
    TimerS1Request,
)
from loto.timer_s1_campaign.geometry import compile_history
from loto.timer_s1_campaign.provenance import ProvenanceError, validate_provenance


def _failure(
    request: TimerS1Request,
    code: str,
    message: str,
    status: ProviderStatus = ProviderStatus.EXECUTION_PENDING,
) -> TimerS1FailureResponse:
    return TimerS1FailureResponse(
        run_id=request.run_id,
        status=status,
        error_code=code,
        error_message=message,
    )


def handle_request(request: TimerS1Request) -> TimerS1FailureResponse:
    if request.operation.value == "identity":
        return _failure(
            request,
            "PR_A_PROVIDER_SKELETON",
            "Timer-S1 identity is registered, but real runtime is intentionally not executed.",
        )
    try:
        compile_history(
            request.game,
            request.history,
            request.context_length,
            request.timeline_mode,
        )
        validate_provenance(request)
    except ProvenanceError as exc:
        return _failure(request, str(exc), "provenance validation blocked model loading")
    except ValueError as exc:
        return _failure(
            request,
            "REQUEST_VALIDATION_FAILED",
            str(exc),
            ProviderStatus.FAILED,
        )
    return _failure(
        request,
        "REAL_RUNTIME_DEFERRED_TO_PR_B",
        "PR-A stops before checkpoint import, model load, or inference.",
    )
