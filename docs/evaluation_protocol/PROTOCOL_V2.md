# Evaluation Protocol v2

## Status

```text
IMPLEMENTED_FOUNDATION
HIT_AT_1_CANONICAL_PRIMARY
LEGACY_V1_READABLE
HISTORICAL_ARTIFACTS_IMMUTABLE
RESEARCH_V3_ADOPTION_NOT_INCLUDED
```

## Scope

This document defines the common evaluation protocol foundation added by
`fix/evaluation-protocol-completeness-v1`. It does not open Holdout or Prospective data, change
model providers, redefine Runtime Certification or Data Access Ledger, or modify API health
endpoints.

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

Metric definitions record display name, optimization direction, scope, aggregation, point and
probabilistic applicability, and explicit legacy aliases. Aliases are resolved before comparison;
conflicting values for aliases of the same canonical metric are rejected.

Representative aliases:

```text
within_1_rate       -> hit_at_1
element_within_1    -> hit_at_1
mean_within_1       -> hit_at_1
position_within_1   -> position_hit_at_1
row_within_1        -> all_positions_hit_at_1
position_mae        -> mae
position_mse        -> mse
position_rmse       -> rmse
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

Additional explicitly identified statistical baselines are allowed and change the protocol hash.
Removing any required baseline is rejected.

## Protocol v2 fields

`EvaluationProtocolV2` is a strict, frozen Pydantic v2 contract with unknown-field and non-finite
number rejection. Its fields are:

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

## Comparison budget hash

The independent `comparison_budget_hash` covers:

```text
search_space_identity
resource_budget
```

The resource budget records CPU count, GPU count, GPU memory bytes, wall-time seconds, maximum
trials and parallel trials. A resource-budget change changes the comparison budget hash.

## Field-level protocol diff

A protocol diff contains:

```text
comparable
left_hash
right_hash
differences
```

Every difference contains:

```text
path
left
right
severity
```

Severities are:

```text
RESULT_AFFECTING
SCHEMA_INCOMPATIBLE
```

Any difference, including a hash-only mismatch, makes `comparable=false` and causes the assertion
API to raise `ProtocolComparisonRefused`.

## All-seed aggregation

Every approved seed must be present exactly once. Partial seed sets and best-seed-only input are
rejected. Each metric summary stores:

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

Worst direction is derived from the metric registry: low values are worst for maximize metrics and
high values are worst for minimize metrics.

## Legacy compatibility and historical immutability

`read_protocol_artifact` retains read access to legacy protocol artifacts. Protocol v1 and protocol
v2 are not silently comparable; their schema difference is emitted and comparison is refused.

`write_protocol_artifact` refuses to overwrite an existing path by default and writes new v2
artifacts through a same-directory temporary file, fsync and atomic replace. This PR performs no
historical backfill and does not claim information absent from an original run.

## Integration boundary

This PR provides the common contracts and decision functions. It intentionally does not rewrite
`src/loto/orchestration/research_v3.py` to fabricate data, split, feature, search-space or resource
identities that the current entry point does not collect. Adoption by that orchestrator requires a
separate bounded migration that supplies real immutable identities and preserves its existing
Holdout seal and leakage controls.

The next planned cross-cutting PR is `feat/telemetry-contract-v1`.
