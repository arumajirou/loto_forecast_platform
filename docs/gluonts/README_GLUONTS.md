# GluonTS isolated provider foundation

Status: `PARTIALLY_VERIFIED`

This directory documents the first implementation phase of the GluonTS integration. It does not
claim model runtime success.

## Why two environments exist

The repository root pins `torch==2.9.1`. GluonTS 0.16.3 accepts Torch versions below 3, while
GluonTS 0.17.0 requires Torch 2.10 or newer. Installing the latest release into the root environment
would therefore violate the existing Torch contract.

| Lane | GluonTS | Torch | Purpose |
|---|---:|---:|---|
| `compat` | 0.16.3 | 2.9.1 | compatible implementation lane |
| `latest` | 0.17.0 | >=2.10,<3 | current-upstream certification lane |

Both lanes must communicate through the JSON-safe Pydantic contract in
`src/loto/adapters/gluonts/protocol.py`. No GluonTS, Torch, Lightning, Predictor, or Dataset Python
object may cross the process boundary.

## Current phase contents

- version-isolated `pyproject.toml` files,
- provider identity entry points,
- strict request and response models,
- explicit draw-sequence versus calendar-time semantics,
- outer-worker and GPU concurrency limits,
- finite-value and fail-closed validation,
- protocol schema SHA-256,
- focused contract tests.

## Certification boundary

The following remain `EXECUTION_PENDING`:

- `uv.lock` generation on the target repository branch,
- package installation,
- all-nine Estimator discovery,
- distribution discovery,
- fit and predict,
- serialize, process exit, deserialize, and re-predict,
- GPU PID, VRAM, device, and CPU fallback evidence,
- chronological CV, OOF, HPO, and accuracy evaluation.

## Local verification

- protocol and environment tests: 9 passed,
- Python compileall: passed,
- maximum Python line length 100: passed,
- compatibility and latest provider identity imports: passed,
- Ruff: blocked because the execution registry did not expose the package,
- isolated `uv.lock`: blocked because the execution registry did not expose GluonTS.

## Next phase

Implement a provider CLI that reads one request JSON document from a file, executes exactly one
bounded operation, atomically writes a response JSON document, and records package versions,
protocol hash, artifact hashes, device evidence, and structured logs.
