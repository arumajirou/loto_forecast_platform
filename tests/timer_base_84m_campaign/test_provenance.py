from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from loto.timer_base_84m_campaign.provenance import ProvenanceError, validate_remote_code_review

REVIEW_PATH = (
    Path(__file__).resolve().parents[2]
    / "audit"
    / "tsfm-runtime"
    / "timer-base-84m"
    / "remote-code-review.json"
)


def review() -> dict:
    return json.loads(REVIEW_PATH.read_text(encoding="utf-8"))


def test_pending_review_fails_closed() -> None:
    with pytest.raises(ProvenanceError, match="unverified"):
        validate_remote_code_review(review())


def test_remote_code_file_set_mismatch_rejected() -> None:
    payload = review()
    payload["files"].pop("modeling_timer.py")
    with pytest.raises(ProvenanceError, match="allowlist"):
        validate_remote_code_review(payload)


def test_remote_code_hash_mismatch_rejected() -> None:
    payload = copy.deepcopy(review())
    payload["files"]["model.safetensors"] = "0" * 64
    with pytest.raises(ProvenanceError, match="weight hash"):
        validate_remote_code_review(payload)
