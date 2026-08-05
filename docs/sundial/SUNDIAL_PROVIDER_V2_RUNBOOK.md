# Sundial provider v2 target-host certification runbook

## Status

`HARNESS_IMPLEMENTED / TARGET_HOST_EXECUTION_PENDING`

This runbook certifies the provider-v2 implementation. It does not reuse the older
`num_samples=1` runtime evidence as proof for the new probabilistic contract.

## Preconditions

- repository branch: `feat/sundial-probabilistic-provider-v2`;
- clean or intentionally recorded worktree;
- pinned snapshot directory ending in
  `3212e42564493f520593e5414af4367fc4b49226`;
- `environments/sundial/uv.lock` present;
- `uv` and `nvidia-smi` available;
- NVIDIA GPU visible to the current user.

## Recommended command

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin

git switch feat/sundial-probabilistic-provider-v2

git status --short --branch

bash scripts/run_sundial_provider_v2_certification.sh \
  /mnt/e/env/ts/loto_forecast_platform \
  /mnt/e/env/huggingface/hub/models--thuml--sundial-base-128m/snapshots/3212e42564493f520593e5414af4367fc4b49226
```

The wrapper keeps the terminal open with `Enterキーで終了します...` and records a launch log.

## Executed matrix

- CPU smoke: `num_samples=1`;
- CUDA sweep: `num_samples=1,3,20,50,100`;
- separate-process replay: two CUDA runs with `num_samples=20`, `seed=42`;
- fixed context: 64 rows, seven position series, one-step horizon;
- point strategy: sample median;
- empirical quantiles: 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95.

## Fail-closed requirements

Every CUDA case must prove all of the following:

- response status `OK`;
- sample shape `[7, num_samples, 1]`;
- finite sample and point values;
- `quantile_source=EMPIRICAL_FROM_GENERATED_SAMPLES`;
- `execution_device=cuda`;
- `gpu_used=true`;
- `cpu_fallback=false`;
- internal peak VRAM greater than zero;
- runner GPU PID equals the directly launched Python PID;
- the same PID is observed externally by `nvidia-smi`;
- external peak VRAM is greater than zero.

The replay verdict must be `EXACT` or `NUMERIC_CLOSE`. `DIVERGENT`, missing evidence, CPU
fallback, or any failed case makes the overall certification fail.

## Artifacts

The harness writes an immutable run directory under:

```text
artifacts/sundial-provider-v2/sundial-v2-YYYYMMDD-HHMMSS/
```

Important outputs:

- `environment.json`;
- `certification-summary.json`;
- `reproducibility.json`;
- `ARTIFACT_MANIFEST.json`;
- `SHA256SUMS`;
- `status.txt`;
- per-case request, response, stdout, stderr, and external GPU-monitor evidence.

`artifacts/sundial-provider-v2/LATEST` points to the latest run directory.

## Formal interpretation

Only this output is a formal pass:

```text
SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS
```

`FAIL` means at least one executed requirement failed. `BLOCKED` means the harness could not begin
because a prerequisite, snapshot, lockfile, interpreter, remote-code review, or GPU tool was absent.
