# TabPFN-TS V2 Runtime Certifier Verification

Status: `PARTIALLY_VERIFIED / MOCK_AND_PROCESS_ORCHESTRATION_PASS / REAL_GPU_PENDING`

## Implemented

- pinned V2 identity and license acceptance;
- offline and telemetry-disabled child environment;
- checkpoint path containment and SHA-256 gate before provider launch and model load;
- CUDA-unavailable and CPU-fallback rejection;
- fixed seed and deterministic CUDA environment settings;
- 37-value finite output validation;
- provider PID, model-parameter device, internal peak VRAM, external `nvidia-smi` PID/UUID/VRAM,
  and post-exit PID-release validation;
- two distinct child processes and same-seed prediction replay;
- response and canonical prediction SHA-256;
- per-process request, response, stdout, stderr, report, and `SHA256SUMS` artifacts;
- CPU smoke classification separated from formal GPU certification.

## Executed locally

| Gate | Result |
|---|---|
| Python compileall | PASS |
| Existing PR1 tests plus PR2 tests | PASS: 74 tests |
| `pytest --import-mode=importlib` with `PYTHONPATH=src` | PASS |
| Real subprocess CPU orchestration fixture | PASS |
| Missing-checkpoint stops before child process | PASS |
| Changed Python line length `<=100` | PASS |
| AST parse | PASS |
| Secret-pattern scan | PASS |
| Large-file scan | PASS |
| Bytecode/cache exclusion | PASS |

Ruff and mypy were not available in the authoring environment and are not reported as passed.

## Not executed

- actual `tabpfn-time-series==1.2.0` environment import;
- real V2 checkpoint deserialization;
- real Loto7 inference;
- RTX 5070 Ti CUDA execution;
- external GPU PID, UUID, and VRAM observation;
- separate-process real prediction replay;
- root full pytest and actionable GitHub Actions;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, or baseline comparison.

## Formal interpretation

This increment proves the certifier's contract, failure boundaries, artifact generation logic, and
subprocess orchestration under dependency-light fixtures. It does not prove that the real model can
load, use CUDA, reproduce predictions, or improve forecast accuracy. Those claims require target-host
artifacts from the command documented in `V2_RUNTIME_CERTIFIER.md`.
