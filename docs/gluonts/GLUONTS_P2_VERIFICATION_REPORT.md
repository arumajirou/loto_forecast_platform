# GluonTS P2 provider protocol verification

## Status

```text
PHASE=GLUONTS_P2
STATUS=PARTIALLY_VERIFIED
RUNTIME_MODEL_SUCCESS=EXECUTION_PENDING
```

## Implemented contract

The isolated provider now accepts exactly these operations:

```text
fit_predict
load_predict
evaluate
backtest
model_discovery
distribution_discovery
runtime_certify
```

The root process and both provider lanes use byte-identical Pydantic protocol source files. Their
Git blob SHA is `12c20d897e9fa4af546e601e63758b797fc46c05`.

## Artifact flow

The root runner writes and retains:

```text
<artifact_root>/<run_id>/<request_id>/request.json
<artifact_root>/<run_id>/<request_id>/response.json
<artifact_root>/<run_id>/<request_id>/stdout.log
<artifact_root>/<run_id>/<request_id>/stderr.log
```

JSON files use deterministic key ordering, a trailing newline, `fsync`, and atomic rename. The
runner records request and response SHA-256 values and rejects timeout, missing response, identity
mismatch, lane mismatch, or protocol schema mismatch.

## Provider CLI

Both lanes support:

```text
python -m loto_gluonts_provider --identity
python -m loto_gluonts_provider --request REQUEST.json --response RESPONSE.json
```

Identity mode does not import GluonTS. Runtime discovery imports GluonTS only inside the isolated
provider and records nine expected PyTorch Estimators and fifteen expected distribution outputs.
Discovery is not treated as fit or prediction certification.

## Local verification

```text
focused_tests=16 passed
provider_cli_tests=5 passed
runner_tests=2 passed
compileall=PASS
python_line_length_max_100=PASS
protocol_source_identity=PASS
```

The focused tests ran against Python 3.13 and Pydantic 2.13.4. The execution registry did not expose
GluonTS or Ruff, so package installation, `uv.lock` resolution, Ruff, real Estimator imports, fit,
predict, serialization, GPU use, and accuracy metrics remain unverified.

## Fail-closed boundaries

- missing GluonTS returns `EXECUTION_PENDING`, not success;
- declared later-phase operations return `EXECUTION_PENDING` without executing a substitute;
- validation or lane mismatch returns `FAILED` with an error;
- `runtime_certify` currently covers import and version facts only;
- no model is marked formally available from class discovery alone.

## Next phase

P3 should run the CLI inside each resolved isolated environment, persist the model and distribution
inventories, distinguish PyTorch Estimator, native Predictor, and extension classes, and record
constructor signatures and import failures. A bounded DeepAR CPU fit/predict smoke belongs after the
inventory is generated and the target package installation is verified.
