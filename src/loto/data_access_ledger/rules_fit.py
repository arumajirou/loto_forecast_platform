from __future__ import annotations

from collections import defaultdict

from loto.data_access_ledger._common import (
    AVAILABILITY_OPERATIONS,
    FIT_ONLY_OPERATIONS,
    HOLDOUT_FORBIDDEN,
    finding,
    slice_signature,
)
from loto.data_access_ledger.contracts import DataAccessLedger, DatasetSlice
from loto.data_access_ledger.enums import (
    AccessOperation,
    DataRole,
    FindingCode,
    FoldRole,
    StateKind,
)
from loto.data_access_ledger.report import ValidationFinding


def validate_fit_tune_and_availability(
    ledger: DataAccessLedger,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for event in ledger.events:
        if event.operation in FIT_ONLY_OPERATIONS:
            invalid = [
                item.data_role.value
                for item in event.input_slices
                if item.data_role is not DataRole.TRAIN
            ]
            if not event.input_slices or invalid:
                findings.append(
                    finding(
                        FindingCode.FIT_SCOPE_VIOLATION,
                        event_id=event.event_id,
                        message=(
                            "fit, scaler, encoder, and feature selection inputs must "
                            "be TRAIN only"
                        ),
                        expected=DataRole.TRAIN.value,
                        observed=str(invalid or "no input_slices"),
                    )
                )

        if event.operation is AccessOperation.TUNE:
            invalid = [
                item.data_role.value
                for item in event.input_slices
                if item.data_role is not DataRole.TRAIN
            ]
            folds: dict[str, dict[FoldRole, list[DatasetSlice]]] = defaultdict(
                lambda: defaultdict(list)
            )
            for item in event.input_slices:
                if item.fold_id is not None and item.fold_role is not None:
                    folds[item.fold_id][item.fold_role].append(item)
            chronology_valid = bool(folds)
            for partitions in folds.values():
                train = partitions.get(FoldRole.TRAIN, [])
                validation = partitions.get(FoldRole.VALIDATION, [])
                if not train or not validation:
                    chronology_valid = False
                    continue
                if max(item.observed_time_end for item in train) >= min(
                    item.observed_time_start for item in validation
                ):
                    chronology_valid = False
            if invalid or not event.input_slices or not chronology_valid:
                findings.append(
                    finding(
                        FindingCode.TUNE_SCOPE_VIOLATION,
                        event_id=event.event_id,
                        message="TUNE requires TRAIN-role chronological inner folds",
                        expected=(
                            "TRAIN outer data with train_end < validation_start per fold"
                        ),
                        observed=str(invalid or "invalid/missing fold partitions"),
                    )
                )
            expected_fold_hash = slice_signature(event.input_slices)
            if (
                event.output_state is None
                or event.output_state.state_kind is not StateKind.HPO_RESULT
                or event.output_state.fold_sha256 != expected_fold_hash
            ):
                findings.append(
                    finding(
                        FindingCode.HPO_FOLD_HASH_MISSING,
                        event_id=event.event_id,
                        message=(
                            "TUNE output must be an HPO_RESULT containing the exact "
                            "fold hash"
                        ),
                        expected=expected_fold_hash,
                        observed=(
                            "missing"
                            if event.output_state is None
                            else str(event.output_state.fold_sha256)
                        ),
                    )
                )

        if event.operation in HOLDOUT_FORBIDDEN and any(
            item.data_role is DataRole.HOLDOUT for item in event.input_slices
        ):
            findings.append(
                finding(
                    FindingCode.HOLDOUT_LEAKAGE,
                    event_id=event.event_id,
                    message="Holdout cannot be used for fit, selection, or tuning",
                    observed=event.operation.value,
                )
            )

        if event.operation in AVAILABILITY_OPERATIONS:
            for item in event.input_slices:
                origin = event.forecast_origin or item.forecast_origin
                if item.available_at > origin:
                    findings.append(
                        finding(
                            FindingCode.FUTURE_AVAILABILITY_VIOLATION,
                            event_id=event.event_id,
                            message="input became available after forecast origin",
                            expected=f"available_at <= {origin.isoformat()}",
                            observed=(
                                f"{item.dataset_id}:{item.available_at.isoformat()}"
                            ),
                        )
                    )
    return findings
