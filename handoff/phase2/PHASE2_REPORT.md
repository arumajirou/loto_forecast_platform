# Phase 2 Runtime Compatibility Audit

- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- source environments: 29
- discovered host runtimes: 40
- mapped environment runtimes: 10
- extra/provider-only runtimes: 30
- CUDA kernel PASS environments: 6
- runtimes advertising sm_120: 6

## Environment statuses

- `CUDA_KERNEL_PASS`: 6
- `IMPORT_VERIFIED_CPU`: 4
- `NO_HOST_RUNTIME`: 19

## Python versions

- `3.11.14`: 1
- `3.12.13`: 2
- `3.13.13`: 7

## Torch versions

- `2.13.0+cu130`: 4
- `2.9.1+cu128`: 2

## CUDA builds

- `12.8`: 2
- `13.0`: 4

## Important

This phase does not load model checkpoints and does not constitute formal model runtime certification.

Formal certification still requires checkpoint load, real input, inference, shape/finite validation, effective device, GPU PID/VRAM, CPU fallback detection, save/reload where applicable, and argument-effect testing.
