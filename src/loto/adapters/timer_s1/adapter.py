from __future__ import annotations

from typing import Any

from loto.adapters.timer_s1.contracts import TimerS1Request
from loto.timer_s1_campaign.provider import handle_request


class TimerS1Adapter:
    """Thin adapter that deliberately delegates to the isolated provider skeleton."""

    model_id = "timer-s1"

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = TimerS1Request.model_validate(payload)
        return handle_request(request).model_dump(mode="json")
