# Feature Availability Registry Data Contract

## Status

`FOUNDATION_ONLY / SYNTHETICALLY_VERIFIED / EXISTING_FEATURES_NOT_MIGRATED`

This contract records whether every model input was knowable at the prediction cutoff. It is a
fail-closed evidence format. A valid synthetic manifest proves only that the contract and validator
behave as specified; it does not prove that any existing or real-data feature pipeline is leak-free.

## Scope

The foundation is independent from model providers and does not modify:

- existing feature builders;
- data acquisition or Raw storage;
- current Train, Validation, Holdout, or Prospective execution;
- provider-specific covariate request contracts;
- scaler, encoder, or feature-selection implementations;
- evaluation metrics, promotion, or prediction locking.

A later migration must wrap one feature family at a time and retain evidence from the real pipeline.

## Strictness

All contracts use Pydantic v2 with:

```python
ConfigDict(
    extra="forbid",
    strict=True,
    frozen=True,
    validate_default=True,
)
```

Unknown keys, implicit Python type coercion, naive datetimes, invalid IANA timezones, unsafe identity
strings, and non-SHA-256 digests are rejected at schema validation.

## Temporal classes

| Class | Meaning | Minimum evidence |
|---|---|---|
| `TARGET_HISTORY` | Lagged target history | `lag >= 1`; only already-known target actuals |
| `PAST_ONLY` | External observation available no later than the cutoff | `available_at <= prediction_cutoff` |
| `KNOWN_FUTURE` | Future-horizon value fixed before prediction | explicit `known_at_prediction_time=true` |
| `STATIC` | Time-invariant or entity-static value | pinned source and revision |
| `UNKNOWN` | Classification not established | always invalid |

`KNOWN_FUTURE` does not mean “available after the prediction was made.” Its value must already be
published, scheduled, or otherwise fixed at the recorded cutoff.

## Split classes

```text
TRAIN
VALIDATION
HOLDOUT
PROSPECTIVE
```

`SplitManifest` windows must be unique, chronological, non-overlapping, and ordered exactly from
Train toward Prospective. Train is mandatory. The feature and split manifests must share the same
`protocol_hash`.

## Contracts

### `FeatureDefinition`

Defines stable feature semantics:

- `feature_name`
- `source_name`
- `source_column`
- `feature_code_hash`
- `temporal_class`
- `lag`
- `timezone`
- `revision`
- `missing_policy`

The canonical feature identity is:

```text
feature_name | source_name | source_column | revision | feature_code_hash
```

A duplicate identity, or two definitions with the same `feature_name`, fails closed.

### `FeatureSource`

Pins the source bytes and release identity:

- `source_name`
- `source_hash`
- `generated_at`
- `available_at`
- `timezone`
- `revision`

`source_hash_expectations` in `FeatureManifest` freezes the expected digest. A changed hash for the
same named source, or multiple hashes for one `(source_name, revision)`, is invalid.

### `FeatureAvailability`

Records the prediction-time assertion:

- `feature_name`
- `source_name`
- `available_at`
- `prediction_cutoff`
- `temporal_class`
- `lag`
- `timezone`
- `known_at_prediction_time`
- `future_target_dependency`
- `revision`

The validator does not infer availability from a column name. It requires explicit evidence.

### `FeatureMaterialization`

Binds source, code, split, and generated feature bytes:

- every required identity, hash, temporal, cutoff, split, revision, and missing-policy field;
- `target_actual_splits`, listing target-actual partitions consumed during generation;
- `materialization_hash`, pinning the output bytes.

Any `target_actual_splits` entry from Validation, Holdout, or Prospective is a hard failure. Train
actuals are permitted only where the feature semantics allow them, such as lagged target history.

### `PreprocessorFitEvidence`

Records one scaler, encoder, selector, or other fitted preprocessor for one transform split:

- preprocessor identity and kind;
- affected feature names;
- `fit_split` and `transform_split`;
- fit-data and code hashes;
- fitted timestamp, timezone, and revision.

Every fitted preprocessor must use `fit_split=TRAIN`. Transforming Validation, Holdout, or
Prospective is allowed only with parameters fitted on Train.

### `FeatureManifest`

The root evidence object binds:

- one prediction cutoff;
- one evaluation `protocol_hash`;
- feature definitions, sources, availability assertions, materializations, preprocessors;
- one `SplitManifest`;
- frozen source-hash expectations.

The validator cross-checks references rather than trusting self-declared booleans in isolation.

## Missing policies

```text
ERROR
DROP_ROW
IMPUTE_TRAIN_ONLY
FORWARD_FILL_PAST_ONLY
ALLOW_NULL
```

A migration must document why its chosen policy is temporally valid. In particular,
`IMPUTE_TRAIN_ONLY` means imputation parameters are fitted only on Train, and
`FORWARD_FILL_PAST_ONLY` may not backfill from a future observation.

## Fail-closed rules

The manifest is invalid when any of the following is observed:

1. `available_at > prediction_cutoff`;
2. generated materialization after the cutoff;
3. unknown, mutable, or unpinned feature/source/preprocessor revision;
4. `future_target_dependency=true`;
5. scaler, encoder, selector, or other fitted state learned outside Train;
6. Validation, Holdout, or Prospective actuals used for feature generation;
7. duplicate feature identity or feature name;
8. changed or inconsistent source hash;
9. `temporal_class=UNKNOWN`;
10. `known_at_prediction_time=false`;
11. source, definition, availability, timezone, split, or protocol reference mismatch;
12. overlapping, reversed, duplicated, or non-chronological split windows.

## Manifest persistence

`write_feature_manifest`:

1. validates the complete manifest;
2. serializes deterministic canonical JSON;
3. writes through a same-directory temporary file and `os.replace`;
4. writes a `<manifest>.sha256` sidecar;
5. refuses overwrite by default.

`read_feature_manifest` verifies the sidecar, rejects duplicate JSON keys, validates the strict
schema, and executes the fail-closed validator again.

## Relationship to existing controls

This foundation complements rather than replaces:

- `loto.data.provenance.check_provenance`, which checks normalized-frame lineage completeness;
- `loto.evaluation.sentinel`, which runs negative controls and a causality probe;
- `loto.evaluation.splits`, which creates chronological folds;
- `loto.evaluation.protocol`, which prevents cross-protocol metric comparison;
- provider-specific covariate contracts in open Draft PRs.

The Registry adds feature-level source/revision/cutoff/materialization/preprocessor evidence that
those components do not currently combine into one common manifest.

## Non-claims

```text
existing feature inventory migrated=false
real source hashes verified=false
real scaler or encoder fit scope verified=false
real Validation/Holdout/Prospective feature lineage verified=false
real-data leakage absence proven=false
production eligibility=false
```
