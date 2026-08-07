from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.feature_availability import (
    DataSplit,
    FeatureAvailability,
    FeatureAvailabilityError,
    FeatureDefinition,
    FeatureManifest,
    FeatureMaterialization,
    FeatureSource,
    ManifestIntegrityError,
    MissingPolicy,
    PreprocessorFitEvidence,
    PreprocessorKind,
    SplitManifest,
    SplitWindow,
    TemporalClass,
    ValidationIssueCode,
    assert_feature_manifest_valid,
    canonical_manifest_bytes,
    read_feature_manifest,
    validate_feature_manifest,
    write_feature_manifest,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64
CUTOFF = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)


def valid_manifest(**changes: object) -> FeatureManifest:
    source = FeatureSource(
        source_name="official_draws",
        source_hash=HASH_A,
        generated_at=CUTOFF - timedelta(days=2),
        available_at=CUTOFF - timedelta(days=2),
        timezone="UTC",
        revision="draws-2026-08-04",
    )
    definition = FeatureDefinition(
        feature_name="n1_lag_1",
        source_name="official_draws",
        source_column="n1",
        feature_code_hash=HASH_B,
        temporal_class=TemporalClass.TARGET_HISTORY,
        lag=1,
        timezone="UTC",
        revision="draws-2026-08-04",
        missing_policy=MissingPolicy.ERROR,
    )
    availability = FeatureAvailability(
        feature_name="n1_lag_1",
        source_name="official_draws",
        available_at=CUTOFF - timedelta(days=2),
        prediction_cutoff=CUTOFF,
        temporal_class=TemporalClass.TARGET_HISTORY,
        lag=1,
        timezone="UTC",
        known_at_prediction_time=True,
        future_target_dependency=False,
        revision="draws-2026-08-04",
    )
    materialization = FeatureMaterialization(
        feature_name="n1_lag_1",
        source_name="official_draws",
        source_hash=HASH_A,
        source_column="n1",
        feature_code_hash=HASH_B,
        generated_at=CUTOFF - timedelta(days=1),
        available_at=CUTOFF - timedelta(days=2),
        prediction_cutoff=CUTOFF,
        temporal_class=TemporalClass.TARGET_HISTORY,
        lag=1,
        timezone="UTC",
        fit_split=DataSplit.TRAIN,
        transform_split=DataSplit.VALIDATION,
        known_at_prediction_time=True,
        future_target_dependency=False,
        revision="draws-2026-08-04",
        missing_policy=MissingPolicy.ERROR,
        target_actual_splits=(DataSplit.TRAIN,),
        materialization_hash=HASH_C,
    )
    preprocessor = PreprocessorFitEvidence(
        preprocessor_name="standard_scaler_n1",
        preprocessor_kind=PreprocessorKind.SCALER,
        feature_names=("n1_lag_1",),
        fit_split=DataSplit.TRAIN,
        transform_split=DataSplit.VALIDATION,
        fit_data_hash=HASH_D,
        preprocessor_code_hash=HASH_E,
        fitted_at=CUTOFF - timedelta(days=1),
        timezone="UTC",
        revision="scaler-v1",
    )
    split_manifest = SplitManifest(
        split_id="numbers4-temporal-v1",
        protocol_hash=HASH_F,
        generated_at=CUTOFF - timedelta(days=1),
        timezone="UTC",
        windows=(
            SplitWindow(
                split=DataSplit.TRAIN,
                start_at=CUTOFF - timedelta(days=100),
                end_at=CUTOFF - timedelta(days=30),
                row_start=0,
                row_end=70,
            ),
            SplitWindow(
                split=DataSplit.VALIDATION,
                start_at=CUTOFF - timedelta(days=30),
                end_at=CUTOFF - timedelta(days=20),
                row_start=70,
                row_end=80,
            ),
            SplitWindow(
                split=DataSplit.HOLDOUT,
                start_at=CUTOFF - timedelta(days=20),
                end_at=CUTOFF - timedelta(days=10),
                row_start=80,
                row_end=90,
            ),
            SplitWindow(
                split=DataSplit.PROSPECTIVE,
                start_at=CUTOFF - timedelta(days=10),
                end_at=CUTOFF,
                row_start=90,
                row_end=100,
            ),
        ),
    )
    payload: dict[str, object] = {
        "manifest_id": "feature-manifest-001",
        "protocol_hash": HASH_F,
        "generated_at": CUTOFF - timedelta(hours=1),
        "prediction_cutoff": CUTOFF,
        "timezone": "UTC",
        "definitions": (definition,),
        "sources": (source,),
        "availabilities": (availability,),
        "materializations": (materialization,),
        "preprocessors": (preprocessor,),
        "split_manifest": split_manifest,
        "source_hash_expectations": {"official_draws": HASH_A},
    }
    payload.update(changes)
    return FeatureManifest(**payload)


def issue_codes(manifest: FeatureManifest) -> set[ValidationIssueCode]:
    return {issue.code for issue in validate_feature_manifest(manifest).issues}


def replace_model(model, **changes):
    return model.model_copy(update=changes)


def test_valid_synthetic_manifest_passes() -> None:
    report = assert_feature_manifest_valid(valid_manifest())
    assert report.valid is True
    assert report.checked_feature_count == 1


def test_strict_unknown_field_rejected() -> None:
    payload = valid_manifest().model_dump(mode="python")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        FeatureManifest.model_validate(payload)


def test_manifest_writer_is_deterministic_atomic_and_verified(tmp_path: Path) -> None:
    manifest = valid_manifest()
    target, sidecar = write_feature_manifest(tmp_path / "feature_manifest.json", manifest)
    assert target.read_bytes() == canonical_manifest_bytes(manifest)
    assert sidecar.read_text().endswith("  feature_manifest.json\n")
    assert read_feature_manifest(target) == manifest
    with pytest.raises(FileExistsError):
        write_feature_manifest(target, manifest)


def test_manifest_tamper_is_rejected(tmp_path: Path) -> None:
    target, _ = write_feature_manifest(tmp_path / "feature_manifest.json", valid_manifest())
    target.write_bytes(target.read_bytes().replace(b"n1_lag_1", b"n1_lag_2", 1))
    with pytest.raises(ManifestIntegrityError, match="SHA-256 mismatch"):
        read_feature_manifest(target)


def test_available_after_cutoff_fails_closed() -> None:
    manifest = valid_manifest()
    availability = replace_model(
        manifest.availabilities[0], available_at=CUTOFF + timedelta(seconds=1)
    )
    materialization = replace_model(
        manifest.materializations[0], available_at=CUTOFF + timedelta(seconds=1)
    )
    changed = replace_model(
        manifest,
        availabilities=(availability,),
        materializations=(materialization,),
    )
    assert ValidationIssueCode.AVAILABLE_AFTER_PREDICTION_CUTOFF in issue_codes(changed)


def test_unknown_revision_fails_closed() -> None:
    manifest = valid_manifest()
    definition = replace_model(manifest.definitions[0], revision="UNPINNED")
    changed = replace_model(manifest, definitions=(definition,))
    assert ValidationIssueCode.UNKNOWN_REVISION in issue_codes(changed)


def test_future_target_dependency_fails_closed() -> None:
    manifest = valid_manifest()
    availability = replace_model(manifest.availabilities[0], future_target_dependency=True)
    changed = replace_model(manifest, availabilities=(availability,))
    assert ValidationIssueCode.FUTURE_TARGET_DEPENDENCY in issue_codes(changed)


@pytest.mark.parametrize(
    "fit_split",
    [DataSplit.VALIDATION, DataSplit.HOLDOUT, DataSplit.PROSPECTIVE],
)
def test_preprocessor_fit_outside_train_fails_closed(fit_split: DataSplit) -> None:
    manifest = valid_manifest()
    preprocessor = replace_model(manifest.preprocessors[0], fit_split=fit_split)
    changed = replace_model(manifest, preprocessors=(preprocessor,))
    assert ValidationIssueCode.PREPROCESSOR_FIT_OUTSIDE_TRAIN in issue_codes(changed)


@pytest.mark.parametrize(
    "actual_split",
    [DataSplit.VALIDATION, DataSplit.HOLDOUT, DataSplit.PROSPECTIVE],
)
def test_post_train_actual_dependency_fails_closed(actual_split: DataSplit) -> None:
    manifest = valid_manifest()
    materialization = replace_model(
        manifest.materializations[0],
        target_actual_splits=(DataSplit.TRAIN, actual_split),
    )
    changed = replace_model(manifest, materializations=(materialization,))
    assert ValidationIssueCode.POST_TRAIN_ACTUAL_DEPENDENCY in issue_codes(changed)


def test_duplicate_feature_identity_fails_closed() -> None:
    manifest = valid_manifest()
    changed = replace_model(
        manifest,
        definitions=(manifest.definitions[0], manifest.definitions[0]),
        availabilities=(manifest.availabilities[0], manifest.availabilities[0]),
        materializations=(manifest.materializations[0], manifest.materializations[0]),
    )
    assert ValidationIssueCode.DUPLICATE_FEATURE_IDENTITY in issue_codes(changed)


def test_changed_source_hash_fails_closed() -> None:
    manifest = valid_manifest()
    source = replace_model(manifest.sources[0], source_hash=HASH_B)
    changed = replace_model(manifest, sources=(source,))
    assert ValidationIssueCode.SOURCE_HASH_CHANGED in issue_codes(changed)


def test_unknown_temporal_class_fails_closed() -> None:
    manifest = valid_manifest()
    definition = replace_model(
        manifest.definitions[0], temporal_class=TemporalClass.UNKNOWN, lag=1
    )
    changed = replace_model(manifest, definitions=(definition,))
    assert ValidationIssueCode.UNKNOWN_TEMPORAL_CLASS in issue_codes(changed)


def test_not_known_at_prediction_time_fails_closed() -> None:
    manifest = valid_manifest()
    availability = replace_model(
        manifest.availabilities[0], known_at_prediction_time=False
    )
    changed = replace_model(manifest, availabilities=(availability,))
    assert ValidationIssueCode.NOT_KNOWN_AT_PREDICTION_TIME in issue_codes(changed)


def test_split_overlap_and_order_fail_closed() -> None:
    manifest = valid_manifest()
    windows = list(manifest.split_manifest.windows)
    windows[1] = replace_model(windows[1], start_at=windows[0].start_at, row_start=10)
    split_manifest = replace_model(manifest.split_manifest, windows=tuple(windows))
    changed = replace_model(manifest, split_manifest=split_manifest)
    assert ValidationIssueCode.SPLIT_ORDER_VIOLATION in issue_codes(changed)


def test_assertion_raises_typed_error() -> None:
    manifest = valid_manifest()
    bad = replace_model(
        manifest,
        preprocessors=(replace_model(manifest.preprocessors[0], fit_split=DataSplit.HOLDOUT),),
    )
    with pytest.raises(FeatureAvailabilityError) as error:
        assert_feature_manifest_valid(bad)
    assert error.value.report.valid is False
