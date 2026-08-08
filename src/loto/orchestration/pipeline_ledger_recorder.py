from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loto.orchestration.pipeline_ledger_oof import PipelineLedgerOofMixin
from loto.orchestration.pipeline_ledger_prospective import PipelineLedgerProspectiveMixin
from loto.orchestration.pipeline_ledger_types import (
    Clock,
    EventDraft,
    PipelineDatasetEvidence,
    PipelineLedgerBlocked,
    PipelineLedgerCloseResult,
    SealAndValidate,
    SliceDraft,
    absolute_path,
    reject_symlink_components,
    utc_datetime,
)
from loto.orchestration.pipeline_ledger_validation import seal_and_validate


class PipelineLedgerRecorder(PipelineLedgerOofMixin, PipelineLedgerProspectiveMixin):
    """Runtime state machine for the staged trusted vertical slice."""

    def __init__(
        self,
        *,
        run_id: str,
        output_dir: Path,
        evidence: PipelineDatasetEvidence,
        seed: int = 0,
        clock: Clock | None = None,
        seal_validator: SealAndValidate | None = None,
    ) -> None:
        self.run_id = run_id
        self.output_dir = absolute_path(output_dir)
        reject_symlink_components(self.output_dir, label="output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.evidence = evidence
        self.seed = seed
        self._clock = clock or (lambda: datetime.now(UTC))
        self._seal_and_validate = seal_validator or seal_and_validate
        self._last_time: datetime | None = None
        self._events: list[EventDraft] = []
        self._expected_oof: set[tuple[str, str]] = set()
        self._predicted_oof: set[tuple[str, str]] = set()
        self._actual_oof: set[tuple[str, str]] = set()
        self._scored_oof: set[tuple[str, str]] = set()
        self._prospective_predict: dict[str, str] = {}
        self._prospective_lock: set[str] = set()
        self._gaps: list[str] = []
        self._closed = False
        self._raw_event_id = self._id("read", evidence.canonical_sha256)
        self._append(
            EventDraft(
                event_id=self._raw_event_id,
                sequence_no=1,
                stage="TRAIN",
                operation="READ",
                occurred_at=self._next_time(),
                actor="loto.orchestration.pipeline_staged",
                input_slices=(self._historical_slice(role="RAW"),),
                actuals_known=True,
                notes=(
                    "Canonical historical input loaded. Downstream model calls are "
                    "limited to explicit Train slices."
                ),
            )
        )

    @property
    def events(self) -> tuple[EventDraft, ...]:
        return tuple(self._events)

    @property
    def gaps(self) -> tuple[str, ...]:
        return tuple(self._gaps)

    def mark_gap(self, code: str) -> None:
        normalized = code.strip()
        if normalized and normalized not in self._gaps:
            self._gaps.append(normalized)

    def close(self) -> PipelineLedgerCloseResult:
        if self._closed:
            raise PipelineLedgerBlocked("pipeline ledger recorder is already closed")
        for model_id, fold_id in sorted(self._expected_oof - self._predicted_oof):
            self.mark_gap(f"OOF_PREDICTION_MISSING:{model_id}:{fold_id}")
        for model_id, fold_id in sorted(self._predicted_oof - self._actual_oof):
            self.mark_gap(f"OOF_ACTUAL_READ_MISSING:{model_id}:{fold_id}")
        for model_id, fold_id in sorted(self._actual_oof - self._scored_oof):
            self.mark_gap(f"OOF_SCORE_MISSING:{model_id}:{fold_id}")
        for forecast_id in sorted(set(self._prospective_predict) - self._prospective_lock):
            self.mark_gap(f"PREDICTION_LOCK_MISSING:{forecast_id}")
        if not self._prospective_predict:
            self.mark_gap("PROSPECTIVE_PREDICTION_MISSING")
        complete = not self._gaps
        created_at = self._events[0].occurred_at
        result = self._seal_and_validate(
            self.run_id,
            created_at,
            self.evidence,
            list(self._events),
            [self.seed],
            self.output_dir,
            list(self._gaps),
            complete,
        )
        self._closed = True
        if result.status != "PASS":
            raise PipelineLedgerBlocked(
                "pipeline ledger blocked downstream commit: "
                + ", ".join(result.coverage_gaps or (result.status,))
            )
        return result

    def _append(self, event: EventDraft) -> None:
        if event.sequence_no != len(self._events) + 1:
            raise PipelineLedgerBlocked("event sequence is not gap-free")
        if self._events and event.occurred_at < self._events[-1].occurred_at:
            raise PipelineLedgerBlocked("event timestamp moved backwards")
        self._events.append(event)

    def _next_time(self) -> datetime:
        value = utc_datetime(self._clock())
        if self._last_time is not None and value <= self._last_time:
            value = self._last_time + timedelta(microseconds=1)
        self._last_time = value
        return value

    def _historical_slice(
        self,
        *,
        role: str,
        row_end: int | None = None,
        forecast_origin: datetime | None = None,
        fold_id: str | None = None,
        fold_role: str | None = None,
    ) -> SliceDraft:
        end = len(self.evidence.observed_times) - 1 if row_end is None else row_end
        origin = forecast_origin or self.evidence.observed_times[end]
        return SliceDraft(
            dataset_id=self.evidence.dataset_id,
            dataset_sha256=self.evidence.canonical_sha256,
            data_role=role,
            row_start=0,
            row_end=end,
            observed_time_start=self.evidence.observed_times[0],
            observed_time_end=self.evidence.observed_times[end],
            available_at=self.evidence.observed_times[end],
            forecast_origin=utc_datetime(origin),
            contains_targets=True,
            contains_actuals=False,
            fold_id=fold_id,
            fold_role=fold_role,
        )

    @staticmethod
    def _ledger_fold(model_id: str, fold_id: str) -> str:
        return f"{model_id}/{fold_id}"

    @staticmethod
    def _hash(payload: Any) -> str:
        from loto.data_access_ledger import sha256_hex

        return sha256_hex(payload)

    def _id(self, prefix: str, *parts: object) -> str:
        digest = self._hash([self.run_id, prefix, *[str(part) for part in parts]])[:24]
        return f"pipeline:{prefix}:{digest}"
