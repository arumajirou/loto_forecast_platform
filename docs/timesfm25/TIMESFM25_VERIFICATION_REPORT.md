# TimesFM 2.5 Verification Report

Status: `PARTIALLY_VERIFIED`.

## Executed in the implementation workspace

- `python -m compileall -q src scripts tests`: **PASS**.
- Focused tests for `tests/adapters/timesfm25` and `tests/timesfm25_campaign`: **22 passed**.
- JSON, YAML, and TOML parse validation: **PASS**.
- Python line-length audit (`<=100`): **PASS**.
- Artifact SHA-256 verification: **PASS** after final manifest generation.

## Not executed

- Ruff: tool unavailable in the connector workspace.
- mypy: tool unavailable in the connector workspace.
- root full pytest: repository checkout and complete dependency environment were unavailable.
- real `timesfm==2.0.2` installation and model-weight download.
- real checkpoint hash re-computation.
- GPU model load, inference, external PID match, VRAM release, or CPU-fallback test.
- Transformers parity, XReg, LoRA, Holdout, and Prospective.

The expected package/checkpoint hashes are pinned as provenance values supplied by the implementation plan; they are not represented as locally re-verified bytes.
