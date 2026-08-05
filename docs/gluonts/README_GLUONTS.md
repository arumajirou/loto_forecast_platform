# GluonTS isolated provider integration

Status: `PARTIALLY_VERIFIED`

This directory documents the version-isolated GluonTS integration. It does not claim real model
runtime success until target-machine evidence is present.

## Runtime lanes

| Lane | GluonTS | Torch | Purpose |
|---|---:|---:|---|
| `compat` | 0.16.3 | 2.9.1 | repository-compatible implementation lane |
| `latest` | 0.17.0 | >=2.10,<3 | current-upstream certification lane |

The latest lane does not alter the root Torch contract. No GluonTS, Torch, Lightning, Predictor, or
Dataset Python object crosses the JSON process boundary.

## Implemented phases

### P1: isolated provider foundation

- version-isolated dependency definitions,
- strict JSON/Pydantic request and response contracts,
- explicit timeline, device, seed, and concurrency policy,
- finite-value and fail-closed validation.

### P2: provider CLI and atomic artifacts

- seven provider operations,
- provider CLIs in both lanes,
- atomic request and response JSON,
- stdout and stderr retention,
- request, response, and protocol SHA-256,
- timeout, identity, lane, and schema rejection.

### P3: runtime inventory

- separate PyTorch Estimator, native Predictor, extension, and distribution categories,
- independent import, export, class, signature, constructor, fit, predict, serialization, and device
  states,
- nine expected PyTorch Estimators and fifteen expected distribution outputs,
- native Predictor and extension discovery,
- validated `runtime_inventory.json`,
- aggregate `artifact_manifest.json`,
- no promotion from discovery alone.

### P4: bounded DeepAR CPU fit/predict

- one epoch and one batch per epoch,
- one layer, hidden size four, and four parallel samples,
- StudentT distribution and one-step horizon,
- shape, finite-value, and actual parameter-device checks,
- `deepar_cpu_smoke.json`,
- no runtime success when target versions are absent.

### P5: Predictor serialize, restart, and reload

- `fit_predict` trains, predicts, verifies, and serializes one bounded DeepAR Predictor,
- the Predictor directory gets a deterministic file inventory and SHA-256 tree,
- the fit process exits,
- `load_predict` runs in a new process,
- manifest, file, dataset, runtime-version, lane, model, and PID identity are verified,
- Predictor deserialization is followed by repeated prediction, shape, finite-value, and CPU-device
  checks,
- `predictor_lifecycle.json` and `lifecycle_manifest.json` bind both process results,
- artifact tampering and same-process reload fail closed.

See `GLUONTS_P5_VERIFICATION_REPORT.md` for the current verification boundary.

## P5 artifact layout

```text
<output>/
├── identity.json
├── predictor/
│   ├── <native GluonTS Predictor files>
│   ├── certification_dataset.json
│   └── predictor_artifact_manifest.json
├── provider-artifacts/
│   └── <run_id>/
│       ├── <fit_request_id>/
│       │   ├── request.json
│       │   ├── response.json
│       │   ├── stdout.log
│       │   ├── stderr.log
│       │   └── artifact_manifest.json
│       ├── <load_request_id>/
│       │   ├── request.json
│       │   ├── response.json
│       │   ├── stdout.log
│       │   ├── stderr.log
│       │   └── artifact_manifest.json
│       └── p5-lifecycle/
│           ├── predictor_lifecycle.json
│           └── lifecycle_manifest.json
├── environment_provenance.json
└── SHA256SUMS
```

## Target-machine commands

```bash
bash environments/gluonts-compat/bootstrap_and_certify.sh
bash environments/gluonts-latest/bootstrap_and_certify.sh
```

Each command performs `uv lock`, `uv sync --frozen`, identity capture, fit/serialize in process 1,
load/re-predict in process 2, provenance generation, and complete artifact hashing. It exits non-zero
unless the full lifecycle is verified.

## Current verification

- P5 focused tests: 12 passed,
- fake constructor→fit→predict→serialize→new-PID load→re-predict path: passed,
- artifact tampering, same PID, version drift, identity mismatch, and non-finite values: rejected,
- compileall: passed,
- maximum changed Python line length: 97,
- real target-lane packages: unavailable in the execution registry.

The current formal lifecycle count is therefore zero.

## Certification boundary

The following remain `EXECUTION_PENDING`:

- isolated lock resolution and real package installation,
- real Predictor serialization and cross-process deserialization,
- real repeated prediction and device evidence,
- all-nine Estimator lifecycle certification,
- GPU PID, VRAM, CUDA device, and CPU fallback evidence,
- chronological CV, OOF, HPO, Holdout, Prospective, and accuracy evaluation.
