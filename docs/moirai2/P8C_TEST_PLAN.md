# P8C Test Plan

## Success paths

- verify complete supported CPU and CUDA campaign fixtures;
- verify all six cases and 24 provider-process evidence records;
- verify source commit/tree and model artifact equality across lanes;
- verify wrapper sealing, source injection, launch evidence, and manifest regeneration.

## Integrity failures

- changed file after sealing;
- unlisted or missing artifact;
- unsafe or duplicate manifest path;
- failed case hidden behind a PASS campaign summary;
- changed response or prediction comparison;
- missing, ragged, non-finite, non-monotonic, or incomplete quantiles;
- point forecast differing from q0.5;
- same reload PID, CPU fallback, or device mismatch;
- missing CUDA PID, GPU UUID, VRAM, or PID-release evidence;
- GPU monitor summary differing from rederived samples;
- missing or mismatched reviewed-lock evidence;
- changed snapshot config or model weight SHA-256;
- dirty source tree, changed source commit/tree, or wrong formal entrypoint;
- partial, reordered, or prepare-only campaign;
- non-seed-1 request or non-local snapshot request.

## Test organization

Synthetic fixture helpers are separated from success, failure, and integrity tests so each test
module remains independently reviewable while retaining the same 37 focused cases.

## Static gates

Run focused pytest, Python compileall, JSON/CSV parsing, line-length inspection, delta and cumulative
SHA-256 verification, and a simple secret-pattern scan. Ruff, mypy, full repository pytest, real
runtime execution, and accuracy evaluation remain separate target-host gates.
