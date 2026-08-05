from __future__ import annotations

from datetime import datetime

import pytest

from loto.toto2_campaign.status_history import (
    StatusEvent,
    canonical_status_events,
    current_status,
)


def test_certified_evidence_supersedes_historical_blocker() -> None:
    status = current_status(canonical_status_events())
    assert status.status == "CERTIFIED"
    assert status.evidence == "runtime-certification.json"
    assert status.supersedes == ("blocked-reason.json",)


def test_unknown_superseded_evidence_fails_closed() -> None:
    events = (
        StatusEvent(
            recorded_at=datetime.fromisoformat("2026-08-01T12:00:00+00:00"),
            status="CERTIFIED",
            evidence="runtime-certification.json",
            supersedes=("missing.json",),
        ),
    )
    with pytest.raises(ValueError, match="unknown"):
        current_status(events)
