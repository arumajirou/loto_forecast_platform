# Evaluation Protocol v2

## Status

```text
IMPLEMENTED_FOUNDATION
HIT_AT_1_CANONICAL_PRIMARY
LEGACY_V1_READABLE
HISTORICAL_ARTIFACTS_IMMUTABLE
CURRENT_OPERATOR_ENVIRONMENT=NATIVE_WINDOWS_ONLY
FORMAL_TIMER_OOF_PROTOCOL_REHASH_REQUIRED
HOLDOUT_CLOSED
PROSPECTIVE_CLOSED
```

## Scope

This document defines the common evaluation protocol foundation. It does not open Holdout or Prospective data, change model providers, redefine Runtime Certification or Data Access Ledger, or modify API health endpoints.

For the current Timer Base 84M campaign, the operator can execute only on native Windows. This does **not** make the protocol Windows-specific; it means the next formal protocol artifacts must bind the identities actually measured on Windows instead of copying historical Linux resource/package values.

## Canonical metric inventory

The canonical primary metric is:

```text
hit_at_1 = Hit@±1
```

Required point-forecast metrics are:

```text
hit_at_1
position_hit_at_1
all_positions_hit_at_1
mae
mse
rmse
```

The canonical deterministic selection order is:

1. higher `hit_at_1`;
2. higher `all_positions_hit_at_1`;
3. lower `mae`;
4. lower `rmse`;
5. stable model ID tie break.

Therefore a candidate with better MAE but worse Hit@±1 cannot be selected.

## Baseline inventory

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

Additional explicitly identified statistical baselines are allowed and change the protocol hash. Removing any required baseline is rejected.

## Timer Base 84M current formal design boundary

Unless intentionally revised and documented before formal execution, the current formal OOF design remains:

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

Historical template hashes generated before the final code-bearing changes are **not valid final execution hashes**. They remain evidence of protocol-template verification only.

## Protocol v2 fields

`EvaluationProtocolV2` is a strict, frozen Pydantic v2 contract with unknown-field and non-finite number rejection. Its fields are:

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

## Current Windows-native fixation requirements

A formal protocol may be generated on native Windows if and only if the following are satisfied:

1. the exact final PR head is fetched and race-guarded;
2. the worktree used for protocol generation is clean;
3. `code_hash` is computed from the raw bytes of `git ls-tree -r --full-tree <HEAD>`;
4. the frozen development snapshot is present on Windows and its expected SHA-256 is verified before any formal OOF read;
5. no database re-query or data substitution is used to recreate a missing snapshot silently;
6. Windows CPU/GPU/resource/package values are measured and recorded from the actual formal host;
7. historical Linux resource/package values are not copied into the Windows protocol;
8. all 10 protocol artifacts are regenerated with the final `git_commit` and `code_hash`;
9. all 10 protocol hashes are unique and round-trip readable;
10. a new `PROTOCOL_SET_SHA256` is calculated from the regenerated set;
11. Holdout and Prospective remain unopened;
12. protocol files are written to a new evidence directory and historical artifacts are not overwritten.

### Windows-safe code hash

PowerShell text pipelines may change encoding or line endings. Use raw subprocess bytes, for example:

```powershell
@'
import hashlib
import subprocess

head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
payload = subprocess.check_output(["git", "ls-tree", "-r", "--full-tree", head])
print("git_commit=" + head)
print("code_hash=" + hashlib.sha256(payload).hexdigest())
'@ | python -
```

## Comparison budget hash

The independent `comparison_budget_hash` covers:

```text
search_space_identity
resource_budget
```

The resource budget records CPU count, GPU count, GPU memory bytes, wall-time seconds, maximum trials and parallel trials. A resource-budget change changes the comparison budget hash.

Because the current formal host is Windows, its resource budget must be measured again. A previous Linux budget is historical evidence only.

## Field-level protocol diff

A protocol diff contains:

```text
comparable
left_hash
right_hash
differences
```

Every difference contains `path`, `left`, `right`, and `severity`. Any result-affecting or schema-incompatible difference makes `comparable=false` and causes the assertion API to refuse comparison.

## All-seed aggregation

Every approved seed must be present exactly once. Partial seed sets and best-seed-only input are rejected. Each metric summary stores:

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

Worst direction is derived from the metric registry.

## Prediction sealing and actual-read boundary

For formal OOF, a prediction record must be persisted and SHA-256 sealed before the corresponding target actual is read. The seal must retain evidence that the target actual had not been read. Prediction mutation or overwrite is rejected.

For the current Timer Base 84M OOF path:

- context must end strictly before `target_draw_no`;
- target identity/date must be checked after prediction sealing;
- Timer request/response must keep `actuals_used=false` during prediction;
- CPU fallback must not be silently accepted where the protocol requires GPU execution;
- output shape and finite values must be verified.

## Legacy compatibility and historical immutability

`read_protocol_artifact` retains read access to legacy protocol artifacts. Protocol v1 and protocol v2 are not silently comparable.

`write_protocol_artifact` refuses to overwrite an existing path by default and writes new v2 artifacts through a same-directory temporary file, fsync and atomic replace. Historical artifacts remain immutable even when the formal execution environment changes from Linux to Windows.

## Current non-claims

```text
final_timer_oof_protocol_hashes_fixed=false
formal_baseline_oof_run=false
formal_timer_oof_run=false
holdout_accessed=false
prospective_accessed=false
accuracy_improvement_claimed=false
champion_selected=false
promotion_performed=false
production_deployment=false
```

The next required step is Windows-side snapshot availability/hash verification followed by final protocol regeneration. Formal OOF must not start before that gate passes.