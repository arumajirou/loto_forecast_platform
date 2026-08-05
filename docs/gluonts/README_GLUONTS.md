# GluonTS isolated provider integration

Status: `PARTIALLY_VERIFIED`

This directory documents the isolated GluonTS integration. It does not claim model runtime success.

## Why two environments exist

The repository root pins `torch==2.9.1`. GluonTS 0.16.3 accepts Torch versions below 3, while
GluonTS 0.17.0 requires Torch 2.10 or newer. Installing the latest release into the root environment
would therefore violate the existing Torch contract.

| Lane | GluonTS | Torch | Purpose |
|---|---:|---:|---|
| `compat` | 0.16.3 | 2.9.1 | compatible implementation lane |
| `latest` | 0.17.0 | >=2.10,<3 | current-upstream certification lane |

Both lanes communicate through the JSON-safe Pydantic contract in
`src/loto/adapters/gluonts/protocol.py`. No GluonTS, Torch, Lightning, Predictor, or Dataset Python
object may cross the process boundary.

## Implemented phases

### P1: isolated provider foundation

- version-isolated `pyproject.toml` files,
- provider identity declarations,
- strict request and response models,
- explicit draw-sequence versus calendar-time semantics,
- outer-worker and GPU concurrency limits,
- finite-value and fail-closed validation,
- protocol schema SHA-256.

### P2: provider protocol and artifact flow

- all seven declared operations,
- provider-local protocol copies with identical Git blob SHA,
- `python -m loto_gluonts_provider` CLI in both lanes,
- atomic canonical request and response JSON,
- immutable stdout and stderr logs,
- request and response SHA-256,
- timeout, identity, lane, and schema-hash rejection,
- import-only model and distribution discovery,
- explicit `EXECUTION_PENDING` for later-phase operations.

See `GLUONTS_P2_VERIFICATION_REPORT.md` for the verification boundary.

## Certification boundary

The following remain `EXECUTION_PENDING`:

- isolated `uv.lock` generation,
- package installation in both lanes,
- persisted runtime inventory from the target environments,
- successful Estimator construction,
- fit and predict,
- serialize, process exit, deserialize, and re-predict,
- GPU PID, VRAM, device, and CPU fallback evidence,
- chronological CV, OOF, HPO, and accuracy evaluation.

## Local verification

- focused protocol, runner, and CLI tests: 16 passed,
- Python compileall: passed,
- maximum Python line length 100: passed,
- root, compatibility, and latest protocol source identity: passed,
- Ruff: blocked because the execution registry did not expose the package,
- isolated `uv.lock`: blocked because the execution registry did not expose GluonTS.

## Next phase

P3 runs model and distribution discovery inside each resolved isolated environment and persists a
runtime inventory that separates PyTorch Estimators, native Predictors, and extensions. Availability
is not certified until loading, input construction, inference, output shape, finite values, and
device evidence pass.
