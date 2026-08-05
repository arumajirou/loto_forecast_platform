# Darts verification report

## Status

`PARTIALLY_VERIFIED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

P1-P10 documented focused runs total 81 passed tests. Those phases retain provider,
model-family, evaluation, historical forecast, ensemble, conformal, provenance, and
fail-closed device contracts described in their phase reports.

## P11 persistence and GPU increment

- focused tests: 13 passed;
- exact six-family persistence coverage: PASS;
- process-terminated save/load and disk reload: PASS_CONTRACT;
- artifact size and SHA-256 integrity: PASS;
- model identity, shape, finite, and numerical prediction replay: PASS;
- global clean-save state removal: PASS;
- Torch companion weight artifact requirement: PASS;
- best and last checkpoint trainer/optimizer/scheduler restoration: PASS_CONTRACT;
- initialized-model weights and encoder restoration: PASS_CONTRACT;
- CPU and CUDA `map_location` device certification: PASS_CONTRACT;
- GPU PID, VRAM, allocated/reserved memory, and CPU fallback rejection: PASS_CONTRACT;
- argument ledger, matrix failure retention, and evidence SHA-256: PASS;
- compileall, AST parse, YAML/JSON parse, and line-length inspection: PASS.

Documented focused increment runs now total 94 tests. They were not all executed together
in one environment, so this is not a single 94-test certification run.

## Blocked

- Ruff was unavailable from the configured package registry;
- `darts==0.46.1` and optional dependencies were unavailable;
- notorch and torch lockfiles could not be generated;
- no real Darts save/load, checkpoint, weights, or cross-device execution occurred;
- no real GPU PID, VRAM, persistence, accuracy, Holdout, or Prospective claim is made;
- GitHub Actions jobs continue to fail before step creation and produce no logs.
