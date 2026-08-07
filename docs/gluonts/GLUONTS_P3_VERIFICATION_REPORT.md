# GluonTS P3 runtime inventory verification

## Status

```text
PHASE=GLUONTS_P3
STATUS=PARTIALLY_VERIFIED
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_MODELS=0
```

## Implemented inventory

Each isolated lane now emits a versioned runtime inventory with four disjoint categories:

```text
PYTORCH_ESTIMATOR
NATIVE_PREDICTOR
EXTENSION
DISTRIBUTION_OUTPUT
```

Each entry tracks these stages independently:

```text
import
export
class
signature
constructor
fit
predict
serialize
device
```

Discovery or signature inspection cannot set `formal_availability=VERIFIED`. PyTorch Estimators
require constructor, fit, predict, and device checks to pass. Native Predictors require predict and
device checks. Distribution outputs require constructor checks.

## Candidate coverage

The unresolved no-GluonTS smoke inventory contains:

```text
expected_pytorch_estimators=9
expected_distribution_outputs=15
native_predictor_placeholders>=1
extension_placeholders>=1
total_candidates=26
formally_verified=0
```

When GluonTS is installed, native Predictor subclasses and extension modules are discovered from the
runtime package rather than being silently conflated with PyTorch Estimators.

## Artifact persistence

For discovery and runtime certification, the root runner validates the inventory schema, lane, and
SHA-256 before persisting:

```text
runtime_inventory.json
artifact_manifest.json
```

The manifest records SHA-256 values for request, response, stdout, stderr, and runtime inventory,
plus the provider return code. Inventory summary and hash round trips are validated; malformed
summary, lane mismatch, or hash mismatch changes the provider response to `FAILED`.

## Defects found during local verification

Two defects were identified before finalizing P3:

1. A Pydantic computed summary serialized into JSON but was rejected as an extra field during
   validation. The summary is now a declared field whose value must match the inventory entries.
2. The inventory hash omitted the trailing newline used by atomic JSON persistence. The hash now
   covers the exact canonical bytes written to disk.

Both defects have regression tests.

## Focused verification

```text
inventory_contract_tests=4 passed
runner_inventory_tests=2 passed
compat_runtime_certify_smoke=PASS
latest_runtime_certify_smoke=PASS
compileall=PASS
maximum_changed_python_line_length=98
inventory_contract_source_identity=PASS
```

The smoke used Python 3.13 and Pydantic 2.13.4. GluonTS was unavailable in the execution registry,
so all 26 candidate entries remained discovery-pending and no runtime success was claimed.

## Remaining certification boundary

The following remain `EXECUTION_PENDING`:

- isolated lock resolution and package installation,
- real constructor calls,
- bounded DeepAR CPU fit and predict,
- output shape and finite-value checks,
- predictor serialization and cross-process reload,
- GPU PID, VRAM, CUDA device, and CPU fallback evidence,
- chronological OOF, Holdout, Prospective, and accuracy metrics.

## Next phase

P4 should resolve and install both isolated environments on the target machine, rerun P3 against the
real packages, compare the two inventories, and execute one bounded DeepAR CPU fit/predict smoke.
No model may be promoted to formally available until every required runtime check passes.
