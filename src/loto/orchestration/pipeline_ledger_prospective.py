from __future__ import annotations

from datetime import datetime

from loto.orchestration.pipeline_ledger_types import (
    EventDraft,
    PipelineLedgerBlocked,
    SliceDraft,
    utc_datetime,
)


class PipelineLedgerProspectiveMixin:
        def record_prospective_prediction(
            self,
            *,
            model_id: str,
            forecast_id: str,
            draw_id: str,
            forecast_origin: datetime,
        ) -> None:
            if forecast_id in self._prospective_predict:
                raise PipelineLedgerBlocked(f"duplicate prospective prediction: {forecast_id}")
            origin = utc_datetime(forecast_origin)
            fit_id = self._id("prospective-fit", model_id, forecast_id)
            self._append(
                EventDraft(
                    event_id=fit_id,
                    sequence_no=len(self._events) + 1,
                    stage="PROSPECTIVE",
                    operation="FIT_MODEL",
                    occurred_at=self._next_time(),
                    actor=f"trusted-vertical-slice:{model_id}",
                    input_slices=(
                        self._historical_slice(
                            role="TRAIN",
                            row_end=len(self.evidence.observed_times) - 1,
                            forecast_origin=origin,
                        ),
                    ),
                    parent_event_ids=(self._raw_event_id,),
                    forecast_origin=origin,
                    actuals_known=False,
                    notes="Champion refit on all historical observations available at origin.",
                )
            )
            feature_hash = self._hash(
                {
                    "canonical_sha256": self.evidence.canonical_sha256,
                    "projection": "prospective_features",
                    "forecast_id": forecast_id,
                }
            )
            features = SliceDraft(
                dataset_id=f"{self.evidence.dataset_id}:prospective-features:{forecast_id}",
                dataset_sha256=feature_hash,
                data_role="PROSPECTIVE_FEATURES",
                row_start=len(self.evidence.observed_times),
                row_end=len(self.evidence.observed_times),
                observed_time_start=origin,
                observed_time_end=origin,
                available_at=self.evidence.observed_times[-1],
                forecast_origin=origin,
                contains_targets=False,
                contains_actuals=False,
                draw_id=draw_id,
            )
            predict_id = self._id("prospective-predict", model_id, forecast_id)
            self._append(
                EventDraft(
                    event_id=predict_id,
                    sequence_no=len(self._events) + 1,
                    stage="PROSPECTIVE",
                    operation="PREDICT",
                    occurred_at=self._next_time(),
                    actor=f"trusted-vertical-slice:{model_id}",
                    input_slices=(features,),
                    parent_event_ids=(fit_id,),
                    forecast_origin=origin,
                    forecast_id=forecast_id,
                    actuals_known=False,
                    notes="Prospective forecast produced without future actual-bearing input.",
                )
            )
            self._prospective_predict[forecast_id] = predict_id

        def record_prediction_lock(self, *, forecast_id: str, verified: bool) -> None:
            predict_id = self._prospective_predict.get(forecast_id)
            if predict_id is None:
                raise PipelineLedgerBlocked(
                    f"prediction lock requires prospective prediction: {forecast_id}"
                )
            if forecast_id in self._prospective_lock:
                raise PipelineLedgerBlocked(f"duplicate prediction lock: {forecast_id}")
            if not verified:
                self.mark_gap(f"FORECAST_SEAL_NOT_VERIFIED:{forecast_id}")
            self._append(
                EventDraft(
                    event_id=self._id("lock", forecast_id),
                    sequence_no=len(self._events) + 1,
                    stage="PROSPECTIVE",
                    operation="LOCK_PREDICTION",
                    occurred_at=self._next_time(),
                    actor="loto.sealing.manifest",
                    parent_event_ids=(predict_id,),
                    forecast_id=forecast_id,
                    actuals_known=False,
                    notes=(
                        "Local forecast seal verified. This is not a trusted-time or "
                        "separate Prediction Lock certification claim."
                    ),
                )
            )
            self._prospective_lock.add(forecast_id)
