from __future__ import annotations

from collections import defaultdict

from loto.data_access_ledger._common import finding, slice_signature
from loto.data_access_ledger.contracts import AccessEvent, DataAccessLedger
from loto.data_access_ledger.enums import (
    AccessOperation,
    FindingCode,
    FindingSeverity,
    FoldRole,
    Stage,
)
from loto.data_access_ledger.report import ValidationFinding


def validate_oof(ledger: DataAccessLedger) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    oof_events = [event for event in ledger.events if event.stage is Stage.OOF]
    fits: dict[tuple[str, int], list[AccessEvent]] = defaultdict(list)
    predicts: dict[tuple[str, int], list[AccessEvent]] = defaultdict(list)

    for event in oof_events:
        assert event.fold_id is not None and event.seed is not None
        key = (event.fold_id, event.seed)
        if event.operation in {
            AccessOperation.FIT_MODEL,
            AccessOperation.FIT_SCALER,
            AccessOperation.FIT_ENCODER,
            AccessOperation.SELECT_FEATURES,
            AccessOperation.CALIBRATE,
        }:
            fits[key].append(event)
            if any(item.fold_role is FoldRole.VALIDATION for item in event.input_slices):
                findings.append(
                    finding(
                        FindingCode.OOF_ORDER_VIOLATION,
                        event_id=event.event_id,
                        message=(
                            "OOF target/future fold cannot be used for fit, "
                            "calibration, or selection"
                        ),
                    )
                )
        if event.operation is AccessOperation.PREDICT:
            predicts[key].append(event)

    for key, predict_events in predicts.items():
        model_fits = [
            item
            for item in fits.get(key, [])
            if item.operation is AccessOperation.FIT_MODEL
        ]
        for predict in predict_events:
            prior = [item for item in model_fits if item.sequence_no < predict.sequence_no]
            if not prior:
                findings.append(
                    finding(
                        FindingCode.OOF_ORDER_VIOLATION,
                        event_id=predict.event_id,
                        message=(
                            "OOF prediction has no earlier model fit for the same "
                            "fold and seed"
                        ),
                    )
                )
                continue
            fit = prior[-1]
            train_slices = [
                item for item in fit.input_slices if item.fold_role is FoldRole.TRAIN
            ]
            validation_slices = [
                item
                for item in predict.input_slices
                if item.fold_role is FoldRole.VALIDATION
            ]
            if not train_slices or not validation_slices or max(
                item.observed_time_end for item in train_slices
            ) >= min(item.observed_time_start for item in validation_slices):
                findings.append(
                    finding(
                        FindingCode.OOF_ORDER_VIOLATION,
                        event_id=predict.event_id,
                        related=[fit.event_id],
                        message=(
                            "OOF chronology requires train_observed_end < "
                            "validation_observed_start"
                        ),
                    )
                )

    by_fold: dict[str, dict[int, str]] = defaultdict(dict)
    for (fold_id, seed), fit_events in fits.items():
        model_fits = [
            item for item in fit_events if item.operation is AccessOperation.FIT_MODEL
        ]
        if model_fits:
            train = [
                item
                for item in model_fits[-1].input_slices
                if item.fold_role is FoldRole.TRAIN
            ]
            by_fold[fold_id][seed] = slice_signature(train)
    for fold_id, signatures in by_fold.items():
        if len(set(signatures.values())) > 1:
            findings.append(
                finding(
                    FindingCode.OOF_SEED_SCOPE_MISMATCH,
                    message="OOF seeds use different training ranges",
                    observed=f"{fold_id}:{signatures}",
                )
            )

    if ledger.expected_seeds:
        expected = set(ledger.expected_seeds)
        folds = {event.fold_id for event in oof_events if event.fold_id is not None}
        for fold_id in sorted(folds):
            observed = {
                event.seed
                for event in oof_events
                if event.fold_id == fold_id
                and event.operation is AccessOperation.PREDICT
            }
            missing = sorted(expected - observed)
            if missing:
                findings.append(
                    finding(
                        FindingCode.OOF_SEED_MISSING,
                        message="OOF fold is missing expected seed predictions",
                        expected=str(sorted(expected)),
                        observed=f"{fold_id}:missing={missing}",
                        severity=FindingSeverity.WARNING,
                    )
                )
    return findings
