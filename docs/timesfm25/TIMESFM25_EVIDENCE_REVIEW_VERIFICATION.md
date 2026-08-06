# TimesFM 2.5 P10 Evidence Review Verification

Status: `PARTIALLY_VERIFIED`.

## Executed

- Evidence-review focused suite: **17 passed**.
- Module, script, and test `compileall`: **PASS**.
- CLI smoke using a synthetic strict-GPU bundle: **PASS**, exit code `0`.
- Python line-length audit (`<=100`): **PASS**.
- Duplicate ZIP member warning is explicitly asserted by the test.
- Outer `REVIEW_SHA256SUMS` verification in the strict-GPU test: **PASS**.

## Covered failure modes

```text
external archive SHA mismatch
sidecar filename mismatch
multiple top-level directories
zip-slip path traversal
duplicate ZIP members
symlink ZIP members
Run ID mismatch
preflight failure
internal SHA256SUMS tampering
status/certification mismatch
strict GPU claim with CPU output device
failed runtime
immutable review-directory collision
partial GPU non-promotion
dirty Git worktree rejection
missing NVIDIA process-sample rejection
```

## Not executed

- Review of a real P9 target-host archive.
- RTX 5070 Ti model load or inference.
- Real GPU PID, VRAM, reload, or CUDA output-device certification.
- Formal promotion of any current TimesFM runtime result.
- Root full pytest, Ruff, mypy, or functional GitHub Actions.

Synthetic strict-GPU evidence validates review logic only. It is not evidence that
TimesFM 2.5 has passed real GPU certification.
