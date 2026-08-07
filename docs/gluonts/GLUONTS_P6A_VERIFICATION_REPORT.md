# GluonTS P6A nine-estimator constructor-contract verification

Status: `PARTIALLY_VERIFIED`

## Objective

P6A creates a version-independent, fail-closed constructor matrix for the nine PyTorch Estimators
already named by the P3 runtime inventory. It does not claim fit, predict, serialization, reload, or
accuracy success.

Canonical model order:

```text
DeepNPTSEstimator
DeepAREstimator
TiDEEstimator
SimpleFeedForwardEstimator
TemporalFusionTransformerEstimator
WaveNetEstimator
DLinearEstimator
PatchTSTEstimator
LagTSTEstimator
```

## Primary-source basis

The minimal smoke defaults follow the GluonTS upstream PyTorch estimator test fixture. The fixture
uses `epochs` for DeepNPTS, while the other eight estimators receive bounded Lightning
`trainer_kwargs`. P6A preserves that distinction instead of forcing one common constructor shape.

Explicit distribution-output combinations are limited to combinations exercised by upstream tests:

- DeepAR: `StudentTOutput`, `ImplicitQuantileNetworkOutput`
- TiDE: `QuantileOutput`
- SimpleFeedForward: `QuantileOutput`
- TemporalFusionTransformer: `StudentTOutput`
- DLinear: `QuantileOutput`
- PatchTST: `QuantileOutput`

WaveNet, LagTST, and DeepNPTS use their default output behavior in P6A. An unlisted explicit
distribution request fails closed and is never silently substituted.

## Contracts

Each estimator profile records:

```text
module
class name
training API family
required constructor fields
bounded smoke defaults
explicitly certified distribution outputs
notes
```

Each runtime matrix entry records independent states for:

```text
module import
class export
constructor signature
constructor execution
planned kwargs
rejected arguments
formal state
errors
```

Formal states are:

```text
EXECUTION_PENDING
DISCOVERED_ONLY
CONSTRUCTED_ONLY
FAILED
```

`CONSTRUCTED_ONLY` is not formal model availability. Fit, predict, finite outputs, device evidence,
serialization, process reload, and evaluation remain separate later checks.

## Runtime tools

Each isolated lane receives the same `p6_models.py` and `p6_inventory_cli.py` sources.

Target-machine commands:

```bash
uv run --project environments/gluonts-compat \
  python -m loto_gluonts_provider.p6_inventory_cli \
  --output artifacts/p6/compat/P6_CONSTRUCTOR_MATRIX.json \
  --construct

uv run --project environments/gluonts-latest \
  python -m loto_gluonts_provider.p6_inventory_cli \
  --output artifacts/p6/latest/P6_CONSTRUCTOR_MATRIX.json \
  --construct
```

The CLI exits with:

```text
0 = all nine requested states completed
1 = at least one explicit failure
2 = one or more entries remain execution-pending
```

The root campaign module validates each matrix schema, lane, operation mode, canonical order, and
SHA-256 before producing a cross-lane comparison.

## Local verification

```text
P6A_LOCAL_TESTS=12 passed
COMPILEALL=PASS
MAX_CHANGED_PYTHON_LINE_LENGTH=96
SHARED_PROFILE_SOURCE_IDENTITY=PASS
PROVIDER_CLI_SOURCE_IDENTITY=PASS
MISSING_RUNTIME_CLASSIFICATION=EXECUTION_PENDING
FORMALLY_VERIFIED_MODELS=0
```

The local test environment did not expose the pinned GluonTS packages. Dependency-injected fake
classes verified all nine constructor paths. This evidence validates the contract and planner, not
real GluonTS constructor execution.

## Fail-closed cases covered

- missing GluonTS module,
- class not exported,
- signature inspection failure,
- unknown constructor argument,
- distribution output not certified for the selected estimator,
- constructor exception,
- missing or reordered estimator entry,
- wrong lane or construct mode,
- matrix SHA-256 mismatch,
- reversed compat/latest aggregation.

## Remaining P6 work

P6B must execute bounded fit, predict, output-shape, finite-value, device, serialize, process reload,
and failure-classification checks per model. No estimator becomes formally available based on P6A
constructor evidence alone.

## Merge policy

The pull request remains Draft. P6A does not enable auto-merge and does not merge the branch.
