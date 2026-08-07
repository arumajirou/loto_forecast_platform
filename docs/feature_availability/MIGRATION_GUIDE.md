# Feature Availability Registry Migration Guide

## Migration policy

Do not bulk-migrate all features in one PR. Migrate one bounded feature family or provider contract
at a time so that source identity, cutoff semantics, preprocessor fit scope, and negative tests can
be reviewed independently.

A migration is incomplete until the real pipeline emits a manifest before the corresponding
prediction is evaluated. A hand-authored example is not runtime evidence.

## Step 1: Freeze the prediction protocol

Record the existing evaluation `protocol_hash` and create a `SplitManifest` that explicitly names
Train, Validation, Holdout, and Prospective windows. Verify chronological order and no overlap.
Do not derive the split manifest after Holdout or Prospective actuals have been opened.

## Step 2: Inventory one feature family

For every feature in the selected family, record a `FeatureDefinition`:

- stable name;
- exact source and source column;
- hash of the feature-generation code;
- temporal class and lag;
- IANA timezone;
- immutable revision;
- missing policy.

Classify uncertainty as `UNKNOWN`; the validator will block it. Do not guess `KNOWN_FUTURE`.

## Step 3: Pin source bytes

Create one `FeatureSource` per source artifact or immutable source snapshot. Hash the actual bytes
used by the feature job. Add the expected digest to `source_hash_expectations`.

Database sources require a deterministic snapshot identity, export digest, or equivalent immutable
query result. A connection string, table name, or row count alone is not a source hash.

## Step 4: Record availability

At prediction creation time, emit `FeatureAvailability` with:

- the cutoff fixed before inference;
- the source publication or availability timestamp;
- `known_at_prediction_time` determined from evidence, not from successful later retrieval;
- explicit future-target dependency status.

For scheduled calendar variables, retain the schedule revision that was available at the cutoff.
For revised economic or external series, use the vintage known at the cutoff rather than the latest
backfilled value.

## Step 5: Record materialization

After the feature job completes, emit `FeatureMaterialization` with source hash, code hash,
materialization hash, generated/available timestamps, cutoff, split identities, and
`target_actual_splits`.

Any use of Validation, Holdout, or Prospective actuals must remain visible and must fail validation.
Do not erase the dependency by copying those values into an intermediate table.

## Step 6: Register fitted preprocessors

Emit one `PreprocessorFitEvidence` record for every scaler, encoder, selector, imputer, learned
embedding, or other data-dependent transformation. The fitted object must be learned on Train only.
Create separate records when the same fitted object transforms multiple later splits.

Save and hash:

- Train rows or deterministic Train snapshot used for fit;
- fitting code;
- preprocessor revision or serialized artifact identity;
- fitted timestamp.

## Step 7: Validate before inference

Call `assert_feature_manifest_valid` before model input is constructed. A failed validation must
block inference or produce a typed non-success state. Do not downgrade registry failures to warnings.

Persist with `write_feature_manifest` before the actual outcome for the prediction becomes known.
The timestamp and SHA-256 sidecar should be included in the prediction-lock artifact set.

## Step 8: Add migration-specific tests

Each migration PR must include at least:

- one representative valid synthetic case;
- cutoff boundary test;
- source revision and source-hash mutation tests;
- future-target dependency test;
- Train-only fit test for every preprocessor kind used;
- Validation, Holdout, and Prospective actual-dependency tests;
- provider-specific covariate shape and identity tests;
- manifest tamper test.

## Step 9: Run real evidence separately

After contract review, execute the migrated feature family on a non-protected development slice.
Inspect the emitted manifest and compare it with the source and preprocessor artifacts. Only then
plan Holdout or Prospective use under a separately approved gate.

A clean Registry result means only that the registered evidence satisfies this contract. Combine it
with negative controls and independent data-access evidence; do not state that leakage is impossible.

## Provider-specific covariate contracts

Open Draft PRs currently contain isolated provider rules such as past-only lengths, known-future
horizon coverage, `known_at_prediction_time`, covariate hashes, and future-actual rejection. A later
migration should adapt those provider-owned records into this common manifest without deleting the
provider checks until parity is demonstrated.

Recommended order:

1. select one provider and one target-only scenario;
2. add one past-only feature family;
3. add one known-future feature family;
4. compare provider-local and common-registry decisions;
5. retain both checks until the common contract covers every provider invariant;
6. migrate another provider in a separate PR.

## Rollback

The foundation is add-only. Revert a migration adapter without deleting previously written evidence.
No existing feature generator should be changed merely to make an invalid manifest pass.
