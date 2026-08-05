# TimesFM 2.5 Verification Report

Status: `PARTIALLY_VERIFIED`.

## Executed in the implementation workspace

- `python -m compileall -q src scripts tests`: **PASS** for the initial implementation.
- Focused tests for `tests/adapters/timesfm25` and `tests/timesfm25_campaign`:
  **23 passed** for the initial implementation.
- Runtime certification bundle tests:
  **14 passed** after adding immutable evidence sealing and verdict generation.
- Certification launcher/module/test `compileall`: **PASS**.
- JSON, YAML, and TOML parse validation: **PASS**.
- Python line-length audit (`<=100`): **PASS**.
- Artifact SHA-256 verification: **PASS** after manifest generation.

The 23-test and 14-test results were separate focused runs; they are not represented
as one combined full-repository pytest execution.

## Runtime certification support added

The target-host launcher now records the provider request and response, subprocess
logs and exit code, environment and Git metadata, NVIDIA process samples, a strict
certification verdict, and a sealed `SHA256SUMS` manifest. Existing run directories
are immutable and cannot be overwritten by the launcher.

The bundle verifier detects missing files, hash mismatches, duplicate manifest
entries, path escapes, and unexpected files added after sealing.

## Not executed

- Ruff: tool unavailable in the connector workspace.
- mypy: tool unavailable in the connector workspace.
- root full pytest: repository checkout and complete dependency environment were unavailable.
- real `timesfm==2.0.2` installation and model-weight download.
- real checkpoint hash re-computation.
- GPU model load, inference, external PID match, VRAM release, or CPU-fallback test.
- strict CUDA output-device certification; native API currently returns CPU NumPy outputs.
- Transformers parity, XReg, LoRA, Holdout, and Prospective.

GitHub Actions run `31055903038` failed on both attempts before exposing any job
steps, and job log retrieval returned `BlobNotFound`. This does not identify a
project command or test failure.

The expected package/checkpoint hashes are pinned as provenance values supplied by
the implementation plan; they are not represented as locally re-verified bytes.
