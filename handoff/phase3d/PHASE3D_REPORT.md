# Phase 3D Runtime Lane Selection

- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- source environments: 29
- Phase 4 smoke allowed now: 8
- blocked pending repair/formal-lane work: 21

## Lane counts

- `CURRENT_CPU_LEGACY`: 4
- `CURRENT_LEGACY_GPU_COMPAT`: 1
- `CURRENT_MODERN_GPU_CANDIDATE`: 2
- `EXISTING_VENV_FORMAL_COMPAT_REQUIRED`: 7
- `NO_FORMAL_RUNTIME_READY`: 3
- `REPAIR_DECLARED_RUNTIME`: 4
- `REUSABLE_COMPATIBLE_VENV`: 1
- `SEPARATE_FORMAL_LANE_REQUIRED`: 7

## Boundary

This phase performs metadata/runtime-lane selection only.
No dependency is installed or modified. No checkpoint is loaded and no forecast is executed.

## Next

Start Phase 4A with the highest-priority smoke-allowed runtimes.
Each Phase 4 smoke must verify load, real input, inference, shape, finite output, requested/effective device, GPU PID/VRAM, and CPU fallback.
