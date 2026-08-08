from __future__ import annotations

from loto.coverage.ledger_types import CoverageLedgerBlocked, FoldState
from loto.data_access_ledger import (
    AccessEvent,
    AccessOperation,
    DataRole,
    FoldRole,
    Stage,
    sha256_hex,
)


class CoverageRecorderEventsMixin:
    def register_fold(
        self,
        *,
        experiment_id: str,
        model_id: str,
        phase: str,
        test_index: int,
        seed: int,
    ) -> str:
        if self._closed:
            raise CoverageLedgerBlocked("recorder is already closed")
        if test_index <= 0 or test_index >= self.evidence.accessible_rows:
            raise CoverageLedgerBlocked(f"invalid test_index: {test_index}")
        key = f"{experiment_id}:{model_id}:{phase}:{test_index}:{seed}"
        fold_id = f"cov-{sha256_hex(key)[:24]}"
        if fold_id in self.folds:
            raise CoverageLedgerBlocked(f"duplicate fold registration: {fold_id}")
        origin = self.evidence.observed_times[test_index]
        fit_event_id = self._event_id("fit", fold_id)
        self.events.append(
            AccessEvent(
                event_id=fit_event_id,
                run_id=self.run_id,
                sequence_no=len(self.events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.FIT_MODEL,
                occurred_at=self._occurred_at(),
                actor=f"loto.coverage:{experiment_id}:{model_id}",
                input_slices=[
                    self._slice(
                        dataset_id=self.evidence.dataset_id,
                        dataset_sha256=self.evidence.dataset_sha256,
                        data_role=DataRole.TRAIN,
                        row_start=0,
                        row_end=test_index - 1,
                        forecast_origin=origin,
                        contains_targets=True,
                        contains_actuals=False,
                        fold_id=fold_id,
                        fold_role=FoldRole.TRAIN,
                    )
                ],
                parent_event_ids=[self.read_event_id],
                forecast_origin=origin,
                fold_id=fold_id,
                seed=seed,
                actuals_known=True,
                notes=f"{phase} walk-forward fit on historical prefix only.",
            )
        )
        self.folds[fold_id] = FoldState(
            experiment_id=experiment_id,
            model_id=model_id,
            fold_id=fold_id,
            seed=seed,
            phase=phase,
            test_index=test_index,
            fit_event_id=fit_event_id,
        )
        return fold_id

    def record_prediction(self, *, fold_id: str) -> None:
        state = self._state(fold_id)
        if state.predicted:
            raise CoverageLedgerBlocked(f"prediction already recorded: {fold_id}")
        index = state.test_index
        origin = self.evidence.observed_times[index]
        event_id = self._event_id("predict", fold_id)
        self.events.append(
            AccessEvent(
                event_id=event_id,
                run_id=self.run_id,
                sequence_no=len(self.events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.PREDICT,
                occurred_at=self._occurred_at(),
                actor=f"loto.coverage:{state.experiment_id}:{state.model_id}",
                input_slices=[
                    self._slice(
                        dataset_id=f"{self.evidence.dataset_id}:identity",
                        dataset_sha256=self._projection_hash("target-free-identity"),
                        data_role=DataRole.VALIDATION,
                        row_start=index,
                        row_end=index,
                        forecast_origin=origin,
                        contains_targets=False,
                        contains_actuals=False,
                        fold_id=fold_id,
                        fold_role=FoldRole.VALIDATION,
                        draw_id=self.evidence.draw_ids[index],
                    )
                ],
                parent_event_ids=[state.fit_event_id],
                forecast_origin=origin,
                fold_id=fold_id,
                seed=state.seed,
                actuals_known=False,
                notes="Prediction completed before target row materialization.",
            )
        )
        state.predicted = True
        state.predict_event_id = event_id

    def record_actual(self, *, fold_id: str) -> None:
        state = self._state(fold_id)
        if not state.predicted or state.predict_event_id is None:
            raise CoverageLedgerBlocked(f"actual access requires an earlier prediction: {fold_id}")
        if state.actual_read:
            raise CoverageLedgerBlocked(f"actual already recorded: {fold_id}")
        index = state.test_index
        origin = self.evidence.observed_times[index]
        event_id = self._event_id("actual", fold_id)
        self.events.append(
            AccessEvent(
                event_id=event_id,
                run_id=self.run_id,
                sequence_no=len(self.events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.READ_ACTUALS,
                occurred_at=self._occurred_at(),
                actor=f"loto.coverage:{state.experiment_id}:{state.model_id}",
                input_slices=[
                    self._slice(
                        dataset_id=f"{self.evidence.dataset_id}:actuals",
                        dataset_sha256=self._projection_hash("actual-targets"),
                        data_role=DataRole.ACTUALS,
                        row_start=index,
                        row_end=index,
                        forecast_origin=origin,
                        contains_targets=True,
                        contains_actuals=True,
                        fold_id=fold_id,
                        fold_role=FoldRole.VALIDATION,
                        draw_id=self.evidence.draw_ids[index],
                    )
                ],
                parent_event_ids=[state.predict_event_id],
                forecast_origin=origin,
                fold_id=fold_id,
                seed=state.seed,
                actuals_known=True,
                notes="Target row materialized after prediction.",
            )
        )
        state.actual_read = True
        state.actual_event_id = event_id

    def record_score(self, *, fold_id: str) -> None:
        state = self._state(fold_id)
        if not state.actual_read or state.actual_event_id is None:
            raise CoverageLedgerBlocked(f"score requires an earlier actual read: {fold_id}")
        if state.scored:
            raise CoverageLedgerBlocked(f"score already recorded: {fold_id}")
        self.events.append(
            AccessEvent(
                event_id=self._event_id("score", fold_id),
                run_id=self.run_id,
                sequence_no=len(self.events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.SCORE,
                occurred_at=self._occurred_at(),
                actor=f"loto.coverage:{state.experiment_id}:{state.model_id}",
                input_slices=[],
                parent_event_ids=[state.actual_event_id],
                forecast_origin=self.evidence.observed_times[state.test_index],
                fold_id=fold_id,
                seed=state.seed,
                actuals_known=True,
                notes=f"{state.phase} fold scoring completed.",
            )
        )
        state.scored = True
