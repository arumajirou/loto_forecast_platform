"""Append-only correction-chain verification."""

from __future__ import annotations

from .contracts import CorrectionEvidence
from .statuses import EvidenceStatus


def verify_correction_chain(records: list[CorrectionEvidence]) -> list[str]:
    failures: list[str] = []
    if not records:
        return failures
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    expected_subject = records[0].subject_evidence_sha256
    previous_hash: str | None = None
    previous_time = None
    for expected_sequence, record in enumerate(records, start=1):
        if record.sequence_number != expected_sequence:
            failures.append(
                "correction sequence is not contiguous: "
                f"expected={expected_sequence}, actual={record.sequence_number}"
            )
        if record.correction_id in seen_ids:
            failures.append(f"duplicate correction_id: {record.correction_id}")
        if record.record_sha256 in seen_hashes:
            failures.append(f"duplicate correction record hash: {record.record_sha256}")
        if record.subject_evidence_sha256 != expected_subject:
            failures.append("correction subject changed inside one append-only chain")
        if record.previous_correction_sha256 != previous_hash:
            failures.append(
                "correction previous hash mismatch: "
                f"expected={previous_hash}, actual={record.previous_correction_sha256}"
            )
        if previous_time is not None and record.recorded_at_utc < previous_time:
            failures.append("correction timestamps must be non-decreasing")
        seen_ids.add(record.correction_id)
        seen_hashes.add(record.record_sha256)
        previous_hash = record.record_sha256
        previous_time = record.recorded_at_utc
        if record.status == EvidenceStatus.REVOKED and record is not records[-1]:
            failures.append("REVOKED correction must be the terminal chain record")
    return failures
