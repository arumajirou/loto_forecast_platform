from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from loto.timer_base_84m_campaign.provenance import (
    ProvenanceError,
    load_review,
    validate_remote_code_review,
)

REVIEW_PATH = (
    Path(__file__).resolve().parents[2]
    / "audit"
    / "tsfm-runtime"
    / "timer-base-84m"
    / "remote-code-review.json"
)


def review() -> dict:
    return json.loads(REVIEW_PATH.read_text(encoding="utf-8"))


def approved_review() -> dict:
    payload = review()
    for name, digest in payload["files"].items():
        if digest == "UNVERIFIED":
            payload["files"][name] = "1" * 64
    payload["review_status"] = "APPROVED"
    payload["approved"] = True
    payload["trust_remote_code_allowed"] = True
    payload["reviewer"] = "reviewer@example"
    payload["reviewed_at_utc"] = "2026-08-06T03:00:00+00:00"
    return payload


def test_pending_review_fails_closed() -> None:
    with pytest.raises(ProvenanceError, match="unverified"):
        validate_remote_code_review(review())


def test_source_revision_is_explicitly_unpinned() -> None:
    payload = review()
    payload["source_revision"] = payload["observed_source_head"]
    with pytest.raises(ProvenanceError, match="source_revision"):
        validate_remote_code_review(payload)


def test_remote_code_file_set_mismatch_rejected() -> None:
    payload = review()
    payload["files"].pop("modeling_timer.py")
    with pytest.raises(ProvenanceError, match="snapshot file allowlist"):
        validate_remote_code_review(payload)


def test_remote_code_execution_allowlist_mismatch_rejected() -> None:
    payload = review()
    payload["remote_code_files"].append("README.md")
    with pytest.raises(ProvenanceError, match="execution allowlist"):
        validate_remote_code_review(payload)


def test_duplicate_remote_code_entry_rejected() -> None:
    payload = review()
    payload["remote_code_files"].append("modeling_timer.py")
    with pytest.raises(ProvenanceError, match="execution allowlist"):
        validate_remote_code_review(payload)


def test_remote_code_hash_mismatch_rejected() -> None:
    payload = copy.deepcopy(review())
    payload["files"]["model.safetensors"] = "0" * 64
    with pytest.raises(ProvenanceError, match="weight hash"):
        validate_remote_code_review(payload)


def test_unknown_review_field_rejected() -> None:
    payload = review()
    payload["unexpected"] = True
    with pytest.raises(ProvenanceError, match="fields mismatch"):
        validate_remote_code_review(payload)


@pytest.mark.parametrize(
    "reviewed_at_utc",
    [
        "2026-08-06",
        "2026-08-06T12:00:00+09:00",
        "2026-08-06T03:00:00Z",
        "not-a-timestamp",
    ],
)
def test_review_time_must_be_canonical_utc(reviewed_at_utc: str) -> None:
    payload = approved_review()
    payload["reviewed_at_utc"] = reviewed_at_utc
    with pytest.raises(ProvenanceError, match="reviewed_at_utc"):
        validate_remote_code_review(payload)


def test_canonical_approved_review_is_accepted() -> None:
    validate_remote_code_review(approved_review())


def test_duplicate_json_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
    with pytest.raises(ProvenanceError, match="duplicate JSON key"):
        load_review(path)


def test_non_object_review_rejected(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ProvenanceError, match="JSON object"):
        load_review(path)
