# Timer-S1 verification report

## Executed PR-A verification

- Focused pytest after contract hardening: **49 passed**.
- Focused Timer-S1 source coverage: **85%**.
- Python compileall: **PASS**.
- Python AST and JSON/TOML/CSV parsing: **PASS**.
- Provider identity CLI: **PASS**, exit code 2, `status=EXECUTION_PENDING`.
- Invalid-request CLI serialization: **PASS**, exit code 1, unsafe run ID sanitized.
- Python/Markdown/TOML/JSON/CSV lines over 100 characters: **0**.
- Whitespace check: **PASS**.
- Secret-pattern scan: **PASS**, zero matches.
- Files larger than 1 MB: **0**.
- `TIMER_S1_SHA256SUMS`: **PASS** after final hardening update.
- Ruff: **BLOCKED_TOOL_UNAVAILABLE**.
- mypy: **BLOCKED_TOOL_UNAVAILABLE**.

## Contract evidence

- Canonical and mirror identities remain separate.
- Unknown fields and unsupported semantics are rejected.
- Five structural game geometries and horizons 1, 2, and 5 are represented.
- Verified success is limited to `VERIFIED_CPU` and `VERIFIED_GPU`.
- Response shapes are bound to game geometry, context length, nine quantiles, and horizon.
- Point and quantile matrices are finite, exact-shape, monotone, and q0.5-identical.
- Chronology evidence is bound to the selected context and remains duplicate-free.
- CPU and GPU certification evidence cannot be mixed or reduced to self-declared flags.
- Request config, weight-index, and aggregate weight-set hashes are bound to the manifest.
- Snapshot validation requires exact manifest accounting, size/hash verification, offline mode,
  the exact remote-code allowlist, and timezone-aware approved review evidence.
- Remote code is not imported by the provider skeleton.
- Incomplete upstream artifact evidence keeps formal revisions `UNPINNED` and fails closed.

## GitHub Actions boundary

The original PR run and one failed-job retry both ended before any workflow step was created. Three
contemporaneous unrelated PR heads showed the same `steps=[]` pattern. This is classified as
`CI_BLOCKED_RUNNER_START`; it is not evidence of a Ruff, dependency, compile, or pytest failure.

## Not verified

No package installation, checkpoint download, model load, inference, save/reload, GPU process,
16 GiB offload, OOF, Holdout, Prospective, or forecasting-accuracy result is claimed.
