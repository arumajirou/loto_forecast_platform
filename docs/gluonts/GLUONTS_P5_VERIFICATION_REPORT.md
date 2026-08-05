# GluonTS P5 Predictor lifecycle verification

## Status

```text
PHASE=GLUONTS_P5
STATUS=PARTIALLY_VERIFIED
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_LIFECYCLES=0
```

## Implemented lifecycle

P5 uses the existing process-boundary operations in two separate provider processes:

```text
process 1: fit_predict
  -> bounded DeepAREstimator fit
  -> pre-serialization prediction
  -> shape, finite-value, and CPU-device checks
  -> Predictor.serialize(directory)
  -> artifact file inventory and SHA-256 manifest

process 1 exits

process 2: load_predict
  -> artifact manifest and every file SHA-256 verification
  -> Predictor.deserialize(directory)
  -> saved certification dataset verification
  -> repeated prediction
  -> shape, finite-value, CPU-device, and model identity checks
```

A lifecycle is `VERIFIED` only when both stages are verified, the artifact manifest identity is
unchanged, and the fit and load process IDs differ.

## Serialized artifact contract

The Predictor directory contains the native GluonTS serialization output plus:

```text
certification_dataset.json
predictor_artifact_manifest.json
```

The manifest records:

- lane and model class,
- serialization format,
- fit process ID,
- seed, frequency, prediction length, and context length,
- exact GluonTS and Torch runtime versions,
- certification dataset SHA-256,
- pre-reload prediction SHA-256,
- every serialized file path, size, and SHA-256,
- deterministic tree SHA-256.

Absolute paths and parent traversal are rejected. Missing, additional, modified, duplicated, or
renamed files fail artifact verification before deserialization.

## Root orchestration

`loto.adapters.gluonts.p5_cli` invokes the provider twice through the existing atomic runner. The
second invocation is not started unless fit, prediction, device verification, and serialization all
pass.

The aggregate artifacts are:

```text
predictor_lifecycle.json
lifecycle_manifest.json
```

The lifecycle manifest binds both provider response hashes, the Predictor artifact manifest hash,
return codes, and the aggregate lifecycle hash.

## Fail-closed boundaries

- absent target runtime returns `BLOCKED` and does not start reload;
- a non-empty target Predictor directory is never overwritten;
- only one bounded dataset item is accepted by this certification path;
- only `DeepAREstimator` and CPU/auto device requests are accepted;
- same-process reload is rejected;
- runtime version drift between fit and load is rejected;
- manifest, dataset, file inventory, file SHA, tree SHA, lane, model, and process identity are checked;
- prediction values must be finite and the observed shape must equal the prediction horizon;
- actual Predictor parameter devices must be CPU;
- pre- and post-reload predictions are hashed independently; numerical equality is recorded but is
  not required because probabilistic sampling may be stochastic.

## Local focused verification

```text
serialization_contract_tests=5 passed
fake_runtime_fit_serialize_reload_tests=3 passed
provider_fail_closed_tests=2 passed
root_lifecycle_orchestration_tests=2 passed
total=12 passed
compileall=PASS
maximum_changed_python_line_length=97
```

The fake runtime exercised constructor, fit, predict, serialize, directory verification, separate-PID
deserialize, repeated predict, shape, finite-value, and CPU-device checks.

## Defects found during verification

1. The first dataset hash covered frequency and dataset rows but omitted the `schema_version` that was
   persisted. Reload correctly rejected the mismatch. The hash now covers the exact saved payload.
2. A lifecycle test created a new timestamped manifest for reload instead of sharing the fit
   manifest identity, producing a false mismatch. The fixture now reuses one immutable manifest.

Both have regression coverage.

## Target-machine execution

Each lane bootstrap performs:

```text
uv lock
uv sync --frozen
provider identity
fit_predict in provider process 1
process exit
load_predict in provider process 2
environment_provenance.json
SHA256SUMS
```

Commands:

```bash
bash environments/gluonts-compat/bootstrap_and_certify.sh
bash environments/gluonts-latest/bootstrap_and_certify.sh
```

The bootstrap exits non-zero unless the full cross-process lifecycle is verified.

## Remaining certification boundary

The available execution registry did not expose the pinned GluonTS lane packages. The following
remain `EXECUTION_PENDING`:

- isolated lock resolution,
- real GluonTS and Torch installation,
- real Predictor serialization contents,
- real cross-process Predictor deserialization,
- real repeated prediction, shape, finite-value, and CPU-device evidence,
- GPU PID, VRAM, CUDA device, and CPU fallback evidence,
- chronological OOF, Holdout, Prospective, and accuracy metrics.

## Next phase

P6 should generalize the verified lifecycle from the single DeepAR certification fixture to the nine
PyTorch Estimators, preserving per-model constructor arguments, supported distributions, resource
limits, failure classification, and independent runtime evidence.
