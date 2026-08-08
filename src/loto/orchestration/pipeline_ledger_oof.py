from __future__ import annotations

from loto.orchestration.pipeline_ledger_types import (
    EventDraft,
    PipelineLedgerBlocked,
    SliceDraft,
)


class PipelineLedgerOofMixin:
    def register_oof(self, *, model_id: str, fold_id: str) -> None:
        key = (model_id, fold_id)
        if key in self._expected_oof:
            raise PipelineLedgerBlocked(f"duplicate OOF registration: {key}")
        self._expected_oof.add(key)

    def record_oof_prediction(
        self,
        *,
        model_id: str,
        fold_id: str,
        test_index: int,
    ) -> None:
        key = (model_id, fold_id)
        if key not in self._expected_oof:
            raise PipelineLedgerBlocked(f"unregistered OOF prediction: {key}")
        if key in self._predicted_oof:
            raise PipelineLedgerBlocked(f"duplicate OOF prediction: {key}")
        if not 0 < test_index < len(self.evidence.observed_times):
            raise PipelineLedgerBlocked(f"invalid OOF test index for {key}: {test_index}")
        ledger_fold = self._ledger_fold(model_id, fold_id)
        origin = self.evidence.observed_times[test_index]
        fit_id = self._id("fit", model_id, fold_id, self.seed)
        train = self._historical_slice(
            role="TRAIN",
            row_end=test_index - 1,
            forecast_origin=origin,
            fold_id=ledger_fold,
            fold_role="TRAIN",
        )
        self._append(
            EventDraft(
                event_id=fit_id,
                sequence_no=len(self._events) + 1,
                stage="OOF",
                operation="FIT_MODEL",
                occurred_at=self._next_time(),
                actor=f"trusted-vertical-slice:{model_id}",
                input_slices=(train,),
                parent_event_ids=(self._raw_event_id,),
                forecast_origin=origin,
                fold_id=ledger_fold,
                seed=self.seed,
                actuals_known=False,
                notes="Candidate and position adapters fit on history before the test draw.",
            )
        )
        identity_hash = self._hash(
            {
                "canonical_sha256": self.evidence.canonical_sha256,
                "projection": "forecast_identity",
            }
        )
        identity = SliceDraft(
            dataset_id=f"{self.evidence.dataset_id}:forecast-identity",
            dataset_sha256=identity_hash,
            data_role="VALIDATION",
            row_start=test_index,
            row_end=test_index,
            observed_time_start=origin,
            observed_time_end=origin,
            available_at=origin,
            forecast_origin=origin,
            contains_targets=False,
            contains_actuals=False,
            fold_id=ledger_fold,
            fold_role="VALIDATION",
            draw_id=self.evidence.draw_ids[test_index],
        )
        self._append(
            EventDraft(
                event_id=self._id("predict", model_id, fold_id, self.seed),
                sequence_no=len(self._events) + 1,
                stage="OOF",
                operation="PREDICT",
                occurred_at=self._next_time(),
                actor=f"trusted-vertical-slice:{model_id}",
                input_slices=(identity,),
                parent_event_ids=(fit_id,),
                forecast_origin=origin,
                fold_id=ledger_fold,
                seed=self.seed,
                actuals_known=False,
                notes="Decoded prediction completed before target value materialization.",
            )
        )
        self._predicted_oof.add(key)

    def record_oof_actual(
        self,
        *,
        model_id: str,
        fold_id: str,
        test_index: int,
    ) -> None:
        key = (model_id, fold_id)
        if key not in self._predicted_oof:
            raise PipelineLedgerBlocked(f"OOF actual read requires prediction: {key}")
        if key in self._actual_oof:
            raise PipelineLedgerBlocked(f"duplicate OOF actual read: {key}")
        ledger_fold = self._ledger_fold(model_id, fold_id)
        origin = self.evidence.observed_times[test_index]
        actual_hash = self._hash(
            {
                "canonical_sha256": self.evidence.canonical_sha256,
                "projection": "actuals",
            }
        )
        actual = SliceDraft(
            dataset_id=f"{self.evidence.dataset_id}:actuals",
            dataset_sha256=actual_hash,
            data_role="ACTUALS",
            row_start=test_index,
            row_end=test_index,
            observed_time_start=origin,
            observed_time_end=origin,
            available_at=origin,
            forecast_origin=origin,
            contains_targets=True,
            contains_actuals=True,
            fold_id=ledger_fold,
            fold_role="VALIDATION",
            draw_id=self.evidence.draw_ids[test_index],
        )
        self._append(
            EventDraft(
                event_id=self._id("actual", model_id, fold_id, self.seed),
                sequence_no=len(self._events) + 1,
                stage="OOF",
                operation="READ_ACTUALS",
                occurred_at=self._next_time(),
                actor=f"trusted-vertical-slice:{model_id}",
                input_slices=(actual,),
                parent_event_ids=(self._id("predict", model_id, fold_id, self.seed),),
                forecast_origin=origin,
                fold_id=ledger_fold,
                seed=self.seed,
                actuals_known=True,
                notes="Test-draw target values were materialized after prediction.",
            )
        )
        self._actual_oof.add(key)

    def record_oof_score(self, *, model_id: str, fold_id: str) -> None:
        key = (model_id, fold_id)
        if key not in self._actual_oof:
            raise PipelineLedgerBlocked(f"OOF score requires actual read: {key}")
        if key in self._scored_oof:
            raise PipelineLedgerBlocked(f"duplicate OOF score: {key}")
        ledger_fold = self._ledger_fold(model_id, fold_id)
        self._append(
            EventDraft(
                event_id=self._id("score", model_id, fold_id, self.seed),
                sequence_no=len(self._events) + 1,
                stage="OOF",
                operation="SCORE",
                occurred_at=self._next_time(),
                actor=f"trusted-vertical-slice:{model_id}",
                parent_event_ids=(self._id("actual", model_id, fold_id, self.seed),),
                fold_id=ledger_fold,
                seed=self.seed,
                actuals_known=True,
                notes="Per-draw score computed; aggregate evaluation is derived later.",
            )
        )
        self._scored_oof.add(key)
