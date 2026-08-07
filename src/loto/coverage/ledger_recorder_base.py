from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loto.coverage.ledger_io import absolute
from loto.coverage.ledger_types import (
    Clock,
    CoverageDatasetEvidence,
    FoldState,
)
from loto.data_access_ledger import (
    AccessEvent,
    AccessOperation,
    DataRole,
    DatasetSlice,
    FoldRole,
    Stage,
    sha256_hex,
)


class CoverageRecorderBase:
    def __init__(
        self,
        *,
        run_id: str,
        output_dir,
        evidence: CoverageDatasetEvidence,
        expected_seeds: list[int],
        clock: Clock | None = None,
    ) -> None:
        self.run_id = run_id
        self.output_dir = absolute(output_dir)
        self.evidence = evidence
        self.expected_seeds = sorted(set(expected_seeds))
        self.clock = clock or (lambda: datetime.now(UTC))
        self.created_at = self._utc(self.clock())
        self.events: list[AccessEvent] = []
        self.folds: dict[str, FoldState] = {}
        self.coverage_gaps: list[str] = []
        self._last_event_time = self.created_at - timedelta(microseconds=1)
        self._closed = False
        self._record_initial_read()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def _occurred_at(self) -> datetime:
        candidate = self._utc(self.clock())
        if candidate <= self._last_event_time:
            candidate = self._last_event_time + timedelta(microseconds=1)
        self._last_event_time = candidate
        return candidate

    def _event_id(self, operation: str, *parts: object) -> str:
        values = [self.run_id, operation, *[str(part) for part in parts]]
        return f"coverage:{operation}:{sha256_hex(values)[:24]}"

    def _projection_hash(self, name: str) -> str:
        return sha256_hex(
            {
                "dataset_sha256": self.evidence.dataset_sha256,
                "projection": name,
            }
        )

    def _slice(
        self,
        *,
        dataset_id: str,
        dataset_sha256: str,
        data_role: DataRole,
        row_start: int,
        row_end: int,
        forecast_origin: datetime,
        contains_targets: bool,
        contains_actuals: bool,
        fold_id: str | None = None,
        fold_role: FoldRole | None = None,
        draw_id: str | None = None,
    ) -> DatasetSlice:
        return DatasetSlice(
            dataset_id=dataset_id,
            dataset_sha256=dataset_sha256,
            data_role=data_role,
            game_id=self.evidence.game_id,
            series_ids=list(self.evidence.series_ids),
            row_start=row_start,
            row_end=row_end,
            observed_time_start=self.evidence.observed_times[row_start],
            observed_time_end=self.evidence.observed_times[row_end],
            available_at=self.evidence.observed_times[row_end],
            forecast_origin=forecast_origin,
            contains_targets=contains_targets,
            contains_actuals=contains_actuals,
            immutable_source=True,
            fold_id=fold_id,
            fold_role=fold_role,
            draw_id=draw_id,
        )

    def _record_initial_read(self) -> None:
        event_id = self._event_id("read", self.evidence.dataset_sha256)
        origin = self.evidence.observed_times[-1]
        self.events.append(
            AccessEvent(
                event_id=event_id,
                run_id=self.run_id,
                sequence_no=1,
                stage=Stage.TRAIN,
                operation=AccessOperation.READ,
                occurred_at=self._occurred_at(),
                actor="loto.coverage.instrumented",
                input_slices=[
                    self._slice(
                        dataset_id=self.evidence.dataset_id,
                        dataset_sha256=self.evidence.dataset_sha256,
                        data_role=DataRole.RAW,
                        row_start=0,
                        row_end=self.evidence.accessible_rows - 1,
                        forecast_origin=origin,
                        contains_targets=True,
                        contains_actuals=False,
                    )
                ],
                parent_event_ids=[],
                actuals_known=True,
                notes=(
                    "Accessible prefix loaded; protected-test target rows were "
                    "excluded from semantic parsing."
                ),
            )
        )
        self.read_event_id = event_id

    def _state(self, fold_id: str) -> FoldState:
        from loto.coverage.ledger_types import CoverageLedgerBlocked

        try:
            return self.folds[fold_id]
        except KeyError as exc:
            raise CoverageLedgerBlocked(f"unknown fold: {fold_id}") from exc

    def mark_gap(self, code: str) -> None:
        if code not in self.coverage_gaps:
            self.coverage_gaps.append(code)
