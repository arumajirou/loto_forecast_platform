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
- `artifact_manifest.json` with request, response, log, and inventory hashes,
- formal availability guard that prevents discovery-only classes from becoming `VERIFIED`.

See `GLUONTS_P3_VERIFICATION_REPORT.md` for the current verification boundary.

## Artifact layout

```text
<artifact_root>/<run_id>/<request_id>/request.json
<artifact_root>/<run_id>/<request_id>/response.json
<artifact_root>/<run_id>/<request_id>/stdout.log
<artifact_root>/<run_id>/<request_id>/stderr.log
<artifact_root>/<run_id>/<request_id>/runtime_inventory.json
<artifact_root>/<run_id>/<request_id>/artifact_manifest.json
```

## Current verification

- inventory contract tests: 4 passed,
- inventory persistence and fail-closed runner tests: 2 passed,
- provider runtime-certify smoke in both lanes: passed,
- each unresolved lane inventory: 26 candidates and 0 formally verified,
- Python compile checks: passed,
- maximum changed Python line length: 98,
- root, compatibility, and latest inventory source identity: passed.

The local smoke used an environment where GluonTS was unavailable. The observed result is therefore
`EXECUTION_PENDING`, not runtime success.

## Certification boundary

The following remain `EXECUTION_PENDING`:

- isolated `uv.lock` generation,
- GluonTS installation in both target lanes,
- real constructor execution,
- DeepAR fit and predict,
- output shape and finite-value certification,
- serialize, process exit, deserialize, and re-predict,
- GPU PID, VRAM, device, and CPU fallback evidence,
- chronological CV, OOF, HPO, and accuracy evaluation.

## Next phase

P4 should install and lock the isolated environments in the target execution system, run the P3
inventory against the real packages, then perform a bounded DeepAR CPU fit/predict smoke. A model is
not formally available until constructor, input, fit, predict, output, finite-value, and device checks
all pass.
