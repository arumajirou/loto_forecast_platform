# GluonTS isolated provider integration

Status: `PARTIALLY_VERIFIED`

This directory documents the isolated GluonTS integration. It does not claim model runtime success.

## Runtime lanes

| Lane | GluonTS | Torch | Purpose |
|---|---:|---:|---|
| `compat` | 0.16.3 | 2.9.1 | repository-compatible implementation lane |
| `latest` | 0.17.0 | >=2.10,<3 | current-upstream certification lane |

No GluonTS, Torch, Lightning, Predictor, or Dataset Python object crosses the process boundary.

## Implemented phases

### P1: isolated provider foundation

- version-isolated dependency definitions,
- strict JSON/Pydantic request and response contract,
- timeline, device, seed, and concurrency policy,
- finite-value and fail-closed validation.

### P2: provider CLI and atomic artifact flow

- all seven declared provider operations,
- provider CLIs in both lanes,
- atomic request and response JSON,
- stdout and stderr retention,
- request, response, and protocol SHA-256,
- timeout, identity, lane, and schema rejection.

### P3: runtime inventory

- byte-identical inventory contracts in root, compatibility, and latest lanes,
- separate categories for PyTorch Estimators, native Predictors, extensions, and distributions,
- independent import, export, class, signature, constructor, fit, predict, serialization, and device
  states,
- constructor signature capture without instantiation,
- nine expected PyTorch Estimators and fifteen expected distribution outputs,
- native Predictor subclass discovery,
- extension module discovery without silently importing optional dependencies,
- validated `runtime_inventory.json`,
- formal availability guards that prevent discovery-only classes from becoming `VERIFIED`.

### P4: bounded DeepAR CPU certification

- lane-specific `uv lock` and `uv sync --frozen` bootstrap scripts,
- exact GluonTS and Torch runtime-version checks,
- one deterministic DeepAREstimator CPU fit/predict smoke,
- StudentTOutput with one epoch and one batch per epoch,
- output-shape and finite-value checks,
- observed predictor parameter device checks,
- `deepar_cpu_smoke.json` with canonical SHA-256,
- retention of valid failed-smoke evidence,
- artifact-manifest smoke hash,
- promotion of only the certified DeepAREstimator inventory entry.

See `GLUONTS_P4_VERIFICATION_REPORT.md` for the current verification boundary.

## Artifact layout

```text
<artifact_root>/<run_id>/<request_id>/request.json
<artifact_root>/<run_id>/<request_id>/response.json
<artifact_root>/<run_id>/<request_id>/stdout.log
<artifact_root>/<run_id>/<request_id>/stderr.log
<artifact_root>/<run_id>/<request_id>/runtime_inventory.json
<artifact_root>/<run_id>/<request_id>/deepar_cpu_smoke.json
<artifact_root>/<run_id>/<request_id>/artifact_manifest.json
```

## Target execution

Run each lane independently from the repository root:

```bash
bash environments/gluonts-compat/bootstrap_and_certify.sh
bash environments/gluonts-latest/bootstrap_and_certify.sh
```

Each script generates its lane lock, installs only inside that project, executes the real CPU smoke,
records environment provenance, and writes `SHA256SUMS`. It exits unsuccessfully unless fit,
prediction, shape, finite-value, and CPU-device checks all pass.

## Current verification

- DeepAR smoke contract tests: 5 passed,
- smoke artifact runner tests: 3 passed,
- fake-runtime constructor, fit, predict, shape, finite, and CPU-device path: passed,
- Python compile checks: passed,
- bootstrap shell syntax: passed,
- maximum changed Python line length: 98.

The local execution registry did not expose the pinned GluonTS packages. The observed real-runtime
status is therefore `EXECUTION_PENDING`, with 0 formally verified models.

## Certification boundary

The following remain `EXECUTION_PENDING` until the bootstrap scripts succeed on the target machine:

- isolated `uv.lock` generation,
- GluonTS installation in both target lanes,
- real DeepAR construction, fit, and predict,
- observed real output shape and finite values,
- observed real CPU parameter devices,
- serialize, process exit, deserialize, and re-predict,
- GPU PID, VRAM, CUDA device, and CPU fallback evidence,
- chronological CV, OOF, HPO, and accuracy evaluation.

## Next phase

P5 serializes a P4-verified Predictor, exits the provider process, loads it in a new process, and
repeats prediction. Serialization certification requires matching identity, shape, finite values,
and device evidence after process restart.
