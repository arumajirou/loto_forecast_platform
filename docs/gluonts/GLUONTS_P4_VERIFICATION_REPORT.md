# GluonTS P4 DeepAR CPU certification verification

## Status

```text
PHASE=GLUONTS_P4
STATUS=PARTIALLY_VERIFIED
REAL_GLUONTS_INSTALL=EXECUTION_PENDING
REAL_DEEPAR_CPU_FIT_PREDICT=EXECUTION_PENDING
FORMALLY_VERIFIED_MODELS=0
```

P4 implements the real-runtime certification path but does not report it as successful in an
environment where the pinned GluonTS packages cannot be installed.

## Version-isolated bootstrap

Each lane contains `bootstrap_and_certify.sh`. The script performs these actions inside the selected
lane rather than modifying the repository root environment:

```text
uv lock
uv sync --frozen
provider identity capture
runtime_certify request
bounded DeepAR CPU fit/predict
version and device verification
environment_provenance.json
SHA256SUMS
```

The compatibility lane requires GluonTS 0.16.3 and Torch 2.9.1. The latest lane requires GluonTS
0.17.0 and Torch >=2.10,<3. Version mismatch blocks the smoke before model construction.

## Bounded DeepAR smoke

The implemented smoke uses:

```text
model=DeepAREstimator
distribution=StudentTOutput
prediction_length=1
context_length=8
num_layers=1
hidden_size=4
batch_size=4
num_batches_per_epoch=1
num_parallel_samples=4
max_epochs=1
accelerator=cpu
devices=1
threads_per_job=1
```

The provider records these checks independently:

```text
version
import
constructor
dataset
fit
predict
shape
finite
device
```

Formal DeepAR availability requires every check to be `PASS`, an observed output shape equal to
`[prediction_length]`, finite prediction values, and observed predictor parameters on CPU. Class
import or construction alone cannot promote the model.

## Artifact persistence

A runtime-certify invocation may now retain:

```text
request.json
response.json
stdout.log
stderr.log
runtime_inventory.json
deepar_cpu_smoke.json
artifact_manifest.json
```

The root runner validates the smoke schema, lane, declared SHA-256, calculated SHA-256, and persisted
SHA-256. Tampered evidence changes the response to `FAILED`. A genuine failed model smoke is still
retained as `deepar_cpu_smoke.json` when its schema and hash are valid, so failure evidence is not
lost.

## Focused verification

```text
smoke_contract_tests=5 passed
runner_smoke_tests=3 passed
root_compileall=PASS
bootstrap_bash_syntax=PASS
maximum_changed_python_line_length=98
compat_and_latest_smoke_source_identity=EXPECTED
compat_and_latest_cli_source_identity=EXPECTED
```

The smoke contract tests include a fake GluonTS runtime that exercises constructor, fit, predict,
shape, finite-value, and CPU-device checks through the verified path. They also cover blocked
execution, lane mismatch, selective DeepAR inventory promotion, evidence persistence, and SHA
mismatch rejection.

Provider subprocess tests for both repository lanes were added. Final execution against the complete
repository checkout remains dependent on GitHub Actions or the target machine because the local
standalone fixture did not contain the full existing P2 provider protocol.

## Current execution boundary

The available execution registry did not expose the pinned GluonTS packages. Therefore these claims
remain `EXECUTION_PENDING`:

- isolated `uv.lock` resolution,
- installation of GluonTS 0.16.3 and 0.17.0 lanes,
- real DeepAREstimator construction,
- real training and prediction,
- observed output values and shape,
- observed CPU parameter devices,
- predictor serialization and reload,
- GPU PID, VRAM, CUDA device, and CPU fallback evidence,
- chronological OOF, Holdout, Prospective, and accuracy metrics.

## Target execution

Run from the repository root:

```bash
bash environments/gluonts-compat/bootstrap_and_certify.sh
bash environments/gluonts-latest/bootstrap_and_certify.sh
```

A script exits successfully only when the real provider response reports `PARTIALLY_VERIFIED`,
`fit_predict_certified=true`, `device_certified=true`, and smoke outcome `VERIFIED`.

## Next phase

P5 should serialize the verified Predictor, terminate the provider process, load the Predictor in a
new process, and repeat prediction with identity, output shape, finite-value, and device checks. No
serialization certification should be inferred from the P4 in-memory smoke.
