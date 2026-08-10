# Requirements — Windows-only execution

## Functional requirements

1. All operator instructions must be executable on native Windows unless explicitly marked historical or future-platform work.
2. GitHub operations must use exact PR/head race guards before any mutation or formal evidence generation.
3. Formal Timer Base 84M OOF must use Hit@±1 as the primary metric and also report MAE, MSE, RMSE, position Hit@±1, and all-position Hit@±1.
4. Required baselines are random, fixed, mean, median, last, frequency, and statistical AR(1).
5. Formal seed aggregation must retain all approved seeds and report mean, population variance, standard deviation, minimum, maximum, worst value, and worst seed.
6. Prediction records must be immutable and SHA-256 sealed before reading the corresponding target actual.
7. Holdout and Prospective actuals must remain closed until separate explicit gates authorize them.
8. Runtime success must verify load, input, inference, output shape, finite values, device, GPU PID/VRAM when applicable, and CPU fallback behavior.

## Environment requirements

Current verified Windows infrastructure:

```text
runner=az-loto-windows
runner_version=2.336.0
runner_os=Windows
runner_arch=X64
PowerShell=7.6.4
uv_in_windows_ci=exact workflow-selected version
managed_python_in_windows_ci=3.12.13
```

The formal OOF environment may use a different Python/runtime set only if its exact package/resource identity is captured in `EvaluationProtocolV2`.

## Data requirements

- Raw/frozen evidence must not be silently regenerated from a database when the expected snapshot is missing.
- The exact frozen development snapshot must be present on Windows before formal OOF starts.
- Its expected SHA-256 must be verified before any formal target actual is read.
- Raw data is immutable source evidence and must not be overwritten.
- MiniLoto physical DB ID `mini` and logical platform ID `miniloto` must remain explicitly mapped.

## Protocol requirements

- Final protocol artifacts must bind the final documentation/code head actually used for execution.
- `code_hash` must hash raw `git ls-tree -r --full-tree <HEAD>` bytes without PowerShell encoding conversion.
- Resource/package identity must be remeasured on Windows.
- Historical Linux resource/package identity must not be reused as if it were Windows evidence.
- Historical protocol artifacts must not be overwritten.

## Stop conditions

Stop before formal OOF if any of the following is true:

- PR head moved unexpectedly;
- worktree is dirty or contains unrelated changes;
- frozen snapshot is unavailable;
- snapshot SHA-256 does not match the expected identity;
- protocol round trip fails;
- protocol count or hash uniqueness is wrong;
- Holdout or Prospective actuals were opened unexpectedly;
- runtime is using an unrecorded CPU fallback;
- output shape or finite-value validation fails.