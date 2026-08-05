# TiRex-2 requirements

## Scope

Only TiRex-2-owned paths are changed. Shared workers, catalogs, CLI, workflows, root dependency
files, and other time-series foundation models are excluded.

## Functional requirements

- Exact `tirex-2==0.1.1` package identity and fixed model revision.
- SHA-256 verification for `model.ckpt` and `model-config.yaml` before deserialization.
- Pydantic v2 request/response schemas with unknown-key rejection.
- Arbitrary `GameGeometry` and target count; no seven-position assumption in Contract v2.
- Supported prediction lengths: 1, 2, and 5.
- Preserve all native q0.1 through q0.9 values; point forecast equals native q0.5.
- Distinguish local, independent batch, and joint multivariate layouts.
- Fail closed when future covariates are unknown, depend on future actuals, or are sourced after
  prediction issuance.
- Reject silent CUDA-to-CPU fallback.
- Preserve model, tensor, PID, VRAM, dtype, and snapshot evidence fields.

## Non-goals

Fine-tuning, LoRA, streaming execution, OOF, Holdout, Prospective, and shared catalog integration.
