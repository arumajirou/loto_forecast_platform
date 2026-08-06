# Test plan

Focused dependency-light checks cover:

- all five game geometries;
- unknown-field and revision-drift rejection;
- draw-sequence chronology;
- formal context lengths 128, 256, and 512;
- native patch-aligned decode block validation;
- univariate layout constraints;
- exact native tensor shape and all nine quantiles;
- q0.5 point parity;
- non-finite and quantile-crossing rejection;
- CUDA fallback rejection;
- snapshot revision, hash, and size validation;
- trailing-context tensor construction;
- runtime package and model-identity checks through injected fakes;
- external GPU PID CSV parsing and UUID consistency;
- exact two-process `.npy` replay comparison;
- historical blocker supersession semantics;
- Python compilation, line length, structured-file parsing, and secret-pattern scan.

Target-host gates, in order:

1. Generate and manually review the isolated `uv.lock` candidate.
2. Import the pinned packages and load the pinned snapshot offline.
3. Run CPU smoke inference for each formal context/horizon geometry class.
4. Run CUDA certification with child PID, GPU UUID, peak VRAM, and CPU-fallback evidence.
5. Run two separate provider processes and require exact nine-quantile equality.
6. Run Ruff, mypy, focused pytest, then one final full pytest and one actionable CI run.
7. Begin OOF only after runtime certification is formally PASS.

Not yet executed: target-host package resolution, real model load, real CPU/CUDA inference, full
geometry matrix, full repository tests, or forecasting evaluation.
