# TiRex-2 verification report

## Status

`PARTIALLY_VERIFIED / CONTRACT_V2_AND_CERTIFIER_IMPLEMENTED / REAL_RUNTIME_PENDING`

## Executed in the authoring environment

- focused pytest: `38 passed`;
- Python compileall over `src`, `scripts`, and `tests`: `PASS`;
- configured 100-character scan over changed Python/docs/config/CSV files: `PASS`;
- artifact inventory and SHA-256 regeneration: `PASS`.

## Not executed

- Ruff: unavailable from the authoring environment and configured package source;
- mypy: unavailable from the authoring environment;
- isolated `uv lock` and frozen synchronization;
- real `tirex-2==0.1.1` import or model load;
- real q0.1-q0.9 CPU/GPU inference;
- real two-process snapshot reload and prediction reproduction;
- external GPU PID/UUID/VRAM and post-exit release verification;
- full repository pytest;
- GitHub Actions was invoked but blocked before any workflow step (`CI_BLOCKED_RUNNER_START`);
- OOF, Holdout, Prospective, Hit@±1, calibration, or baseline superiority.

Hermetic tests validate project-side contracts and comparison logic only. They are not model
runtime or forecasting-performance evidence.
## P1 reviewed lock workflow

Local pure tests and orchestration smoke are complete. The implementation rejects unsafe package
sources, missing hashes, incompatible direct versions, unrecognized TiRex-2 artifacts, invalid
approval evidence, and installed-lock tampering. A real `uv lock` resolution, complete human
review, frozen synchronization, package import, and model execution remain pending.
