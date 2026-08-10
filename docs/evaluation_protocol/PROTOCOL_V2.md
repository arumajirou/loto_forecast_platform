# Evaluation Protocol v2

> **Document class:** `DESIGN_CONTRACT`  
> **Repository status reference:** [`../STATUS.md`](../STATUS.md)

## Status

```text
IMPLEMENTED_FOUNDATION
HIT_AT_1_CANONICAL_PRIMARY
LEGACY_V1_READABLE
HISTORICAL_ARTIFACTS_IMMUTABLE
HOST_PORTABLE_PROTOCOL
FORMAL_TIMER_OOF_PROTOCOL_FIXATION_REQUIRED
HOLDOUT_CLOSED
PROSPECTIVE_CLOSED
```

PR #240, which added the Timer Base 84M OOF engineering foundation, is merged. That merge does **not** mean formal Timer OOF was executed. The scientific campaign remains tracked separately by GitHub Issue #239 / Linear TAJ-12.

## Scope

This document defines the common evaluation protocol foundation. It does not:

- open Holdout or Prospective data;
- change model provider contracts;
- redefine Runtime Certification or Data Access Ledger;
- make a workstation OS part of the scientific protocol;
- claim forecast superiority.

`EvaluationProtocolV2` is host-portable. A formal run may execute on an approved Windows or Linux host, but its protocol must bind the **actual code/data/resource/package identities measured on that host**. Historical values from another host/run must never be copied merely to preserve an old protocol hash.

## Canonical metric inventory

Primary metric:

```text
hit_at_1 = Hit@±1
```

Required point-forecast metrics:

```text
hit_at_1
position_hit_at_1
all_positions_hit_at_1
mae
mse
rmse
```

Canonical deterministic selection order:

1. higher `hit_at_1`;
2. higher `all_positions_hit_at_1`;
3. lower `mae`;
4. lower `rmse`;
5. stable model ID tie break.

A candidate with better MAE but worse Hit@±1 cannot be selected ahead of the better-Hit@±1 candidate under this ordering.

## Required baseline inventory

Every formal protocol must include at least:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

Additional explicitly identified statistical baselines are allowed and change the protocol identity. Removing a required baseline is rejected.

All model/baseline candidates must use the same eligible folds, target identities, game geometry, horizon, post-processing/reconciliation contract and metric implementation when they are compared.

## Timer Base 84M formal OOF design boundary

Unless intentionally revised **before execution** and recorded as a new protocol identity, the current design contract is:

```text
formal_games=5
layouts=2
prediction_length=1
context_length=96
outer_folds=5
outer_test_size=20
oof_targets_per_game=100
seed_inventory=42,1729,20260730
best_seed_only=false
primary_metric=hit_at_1
required_baselines=7
holdout_opened=false
prospective_opened=false
```

Historical template hashes generated before the final execution identity is fixed are not valid final execution hashes. They remain template/evidence artifacts only.

## Protocol v2 fields

`EvaluationProtocolV2` is a strict, frozen Pydantic v2 contract with unknown-field and non-finite-number rejection.

```text
schema_version
game_geometry
data_snapshot
split_manifest
feature_manifest
metric_manifest
baseline_manifest
alpha
multiplicity_correction
bootstrap_method
bootstrap_repetitions
conformal_method
conformal_alpha
sentinel_inventory
sentinel_repetitions
post_processing_identity
reconciliation_identity
seed_inventory
seed_aggregation_policy
search_space_identity
resource_budget
package_versions
code_hash
git_commit
```

The protocol SHA-256 is calculated from canonical UTF-8 JSON containing every field above.

## Formal fixation requirements

Before a formal OOF run, all of the following must pass:

1. re-fetch the exact execution Git commit and protect against branch/PR races;
2. use a clean worktree/check-out at that exact commit;
3. compute `code_hash` from raw Git tree bytes, not text-normalized shell output;
4. locate the approved frozen development snapshot and verify its expected SHA-256;
5. do not silently recreate a missing snapshot by re-querying a mutable database or API;
6. verify chronological split/feature manifests and their SHA-256 values;
7. measure CPU, RAM, disk, GPU/VRAM, device identity and relevant package versions on the actual formal host;
8. bind that measured resource/package identity into the protocol;
9. regenerate every game/layout protocol artifact using the exact execution `git_commit` and `code_hash`;
10. verify protocol artifacts round-trip and have the expected distinct identities;
11. calculate/fix the protocol-set digest used by the campaign;
12. keep Holdout and Prospective closed;
13. write new evidence to a new Run ID/path; never overwrite historical protocol artifacts.

### Cross-platform raw Git-tree hash

The following Python snippet avoids PowerShell/Bash text-pipeline newline/encoding transformations and works on both Windows and Linux when Git and Python are available:

```python
import hashlib
import subprocess

head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
payload = subprocess.check_output(["git", "ls-tree", "-r", "--full-tree", head])
print("git_commit=" + head)
print("code_hash=" + hashlib.sha256(payload).hexdigest())
```

## Chronology and leakage contract

For each formal target/fold:

```text
BUILD_TRAIN_CONTEXT
FIT_TRAIN_ONLY_COMPONENTS
PREDICT_WITHOUT_TARGET_ACTUAL
PERSIST_AND_SEAL_PREDICTION
READ_TARGET_ACTUAL_AFTER_PREDICTION
SCORE
```

Requirements:

- folds are strictly chronological;
- target/future actuals are absent from the model request/context;
- scaler, encoder, feature selector, calibrator and HPO/tuning components fit only on the Train-eligible slice;
- duplicate target identities are rejected;
- missing/order/domain/availability violations are rejected or handled only by an explicit reviewed protocol rule;
- raw source data is not overwritten;
- a prediction record is immutable and SHA-256 sealed before the corresponding actual is read;
- pretrained weights are not falsely described as fold-trained weights when no fine-tuning occurs.

## Comparison budget hash

The independent `comparison_budget_hash` covers:

```text
search_space_identity
resource_budget
```

The resource budget records the actual formal-run CPU/GPU/resource limits, wall-time/trial limits and parallelism. Changing a result-affecting resource/search budget changes comparison identity.

A resource budget from a historical Windows/Linux run is evidence for that run only.

## Field-level protocol diff

A protocol diff contains:

```text
comparable
left_hash
right_hash
differences
```

Every difference contains `path`, `left`, `right`, and `severity`. Any result-affecting or schema-incompatible difference makes `comparable=false` and the comparison API must refuse silent normalization.

## All-seed aggregation

Every configured/approved seed must be present exactly once. Partial seed sets and best-seed-only input are rejected.

Each metric summary stores:

```text
count
mean
population_variance
standard_deviation
minimum
maximum
worst_value
worst_seed
```

Worst direction is derived from the metric registry. The best seed may be reported diagnostically but cannot stand in for the complete aggregate.

## Prediction sealing and actual-read boundary

For formal OOF, the prediction record must be persisted and SHA-256 sealed before the target actual is read. The seal must preserve evidence that actual access had not occurred at prediction time. Prediction mutation or overwrite is rejected.

For Timer Base 84M:

- context ends strictly before `target_draw_no`;
- target identity/date is verified after prediction sealing;
- Timer request/response retains `actuals_used=false` during prediction;
- output shape and finite values are verified;
- CPU fallback is not presented as GPU success when the protocol requires GPU execution;
- device/PID/VRAM evidence follows runtime-certification requirements.

## Runtime certification relationship

Runtime certification and forecast-quality evaluation are separate gates.

A catalog entry or importable package does not prove runtime success. Runtime evidence must verify actual model load, input, inference, output shape, finite values, effective device, relevant GPU PID/VRAM/CPU-fallback state and cleanup/reload behavior where required.

A runtime-certified model may still fail to beat mandatory baselines in OOF.

## Legacy compatibility and historical immutability

Legacy protocol artifacts remain readable for audit/migration where the implementation supports them. Protocol v1 and v2 are not silently comparable.

New protocol artifacts must use no-clobber/atomic writing behavior. Historical protocol/prediction/evidence artifacts remain immutable even when:

- a PR merges;
- a later host changes OS;
- package versions advance;
- a newer protocol set is generated.

## Current scientific non-claims

As preserved from the PR #240 merge boundary and rechecked during the documentation audit:

```text
formal_timer_oof_protocol_finalized=false
formal_baseline_oof_run=false
formal_timer_oof_run=false
holdout_accessed=false
prospective_accessed=false
accuracy_improvement_claimed=false
champion_selected=false
promotion_performed=false
production_deployment_from_timer_oof=false
```

The next scientific work is the Issue #239 OOF campaign under a newly fixed formal execution identity. Holdout and Prospective must not be opened merely because the engineering foundation has merged.
