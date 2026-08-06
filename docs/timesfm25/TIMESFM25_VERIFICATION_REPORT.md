# TimesFM 2.5 Verification Report

Status: `PARTIALLY_VERIFIED`.

## Executed in the implementation workspace

- Initial provider-contract focused suite: **23 passed**.
- Runtime-certification bundle suite: **14 passed**.
- P8 preflight suite: **10 passed**.
- Runtime launcher preflight-gate test: **1 passed**.
- P9 target-host operator suite: **15 passed**.
- P8 and P9 module, script, and test `compileall`: **PASS**.
- P8 request example validation with the current request contract: **PASS**.
- P8 model manifest validation: **PASS**.
- Python line-length audit (`<=100`): **PASS** for P8 and P9 additions.
- JSON and TOML parse validation for new artifacts: **PASS**.
- Static artifact SHA-256 ledger regeneration: **PASS**.

The focused test counts above are separate runs. They are not represented as one
combined full-repository pytest execution.

## P8 preflight support added

The target-host preparation command can explicitly generate the isolated `uv.lock`.
Every verification after that generation is offline and locked. The preflight
checks exact declared and locked package versions, repository/revision identity,
absolute snapshot location, `config.json`, single-weight topology, weight SHA-256,
runtime imports, PyTorch CUDA availability, CUDA device count, and `nvidia-smi`.

The runtime-certification launcher repeats preflight before provider execution. A
failed preflight creates an immutable sealed failure bundle and does not start model
loading or inference.

Network-disabled subprocess variables are fixed to:

```text
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
UV_OFFLINE=1
PIP_NO_INDEX=1
```

## P9 target-host operator support added

The operator CLI now materializes a unique schema-v2 request, runs preflight,
launches certification in a tmux session or foreground mode, records operator state,
and inspects the sealed runtime bundle without changing its contents.

Finalization is fail-closed. A runtime bundle is archived only after its existing
`SHA256SUMS` verifies. ZIP members are sorted, use fixed timestamps and permissions,
and produce deterministic bytes plus a `.zip.sha256` sidecar outside the sealed run
directory. Tampered, unsealed, incomplete, or internally archived bundles are
rejected.

Operator states distinguish:

```text
PREFLIGHT_RUNNING
PREFLIGHT_FAILED
RUNNING
COMPLETED
PARTIAL
FAILED
INCOMPLETE
CORRUPT
NOT_STARTED
```

## External source cross-check

The Hugging Face model repository currently exposes one `model.safetensors`, one
`config.json`, and reports the same model SHA-256 pinned by the manifest. This is an
external metadata cross-check only; the model bytes were not downloaded or
re-hashed in the implementation workspace.

## Not executed

- Ruff: tool unavailable in the connector workspace.
- mypy: tool unavailable in the connector workspace.
- root full pytest: complete repository dependency environment unavailable.
- target-host `uv.lock` generation.
- real `timesfm==2.0.2` installation in the isolated target environment.
- local snapshot byte re-computation against the model file.
- target-host operator launch through tmux.
- GPU model load, inference, external PID match, VRAM release, or CPU-fallback test.
- strict CUDA output-device certification; native API currently returns CPU NumPy outputs.
- Transformers parity, XReg, LoRA, Holdout, and Prospective.

GitHub Actions runs on the PR head have failed before exposing executable job steps,
and log retrieval returned `BlobNotFound`. This does not identify a project command
or test failure.

The package/checkpoint hashes remain pinned provenance until target-host byte
verification produces a sealed preflight and runtime evidence bundle.
