# P8A Test Plan

## Local unit and source gates

- generate all six cases in fixed order;
- reject unknown or duplicate selected cases;
- validate history, context, horizon, timestamps, covariate names, and exact lengths;
- prove calendar fixtures include gaps while remaining strictly increasing;
- reject absent or mismatched reviewed `uv.lock` entries;
- reject missing snapshot configuration or weight files;
- aggregate all six PASS results into formal success;
- keep subset success non-formal;
- reject missing cases, failed cases, reload mismatch, artifact mismatch, and device mismatch;
- compile Python and enforce a 100-character source-line ceiling.

## Target-host gates

- inspect generated `uv.lock` before frozen synchronization;
- run the frozen import/device preflight;
- run all six CPU cases serially;
- run all six CUDA13 cases serially;
- verify request, response, process, GPU, artifact, and SHA-256 evidence for every case;
- run Ruff, mypy, focused pytest, then one final full pytest;
- inspect one actionable GitHub Actions run.
