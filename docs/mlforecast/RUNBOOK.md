# MLForecast Runtime Certification Runbook

## Purpose

Use this runbook to produce tamper-evident evidence that the frozen
`mlforecast==1.1.0` wheel can be loaded and can complete Core Ridge and
AutoRidge fit, predict, save, load, and re-predict lifecycles.

This is not a real-data accuracy evaluation and does not certify Holdout,
Prospective, GPU, MLflow, PostgreSQL, or multi-seed campaign results.

## Preconditions

- repository checkout containing PR #46 head;
- `uv` available in `PATH`;
- GNU `sha256sum`;
- repository `uv.lock` present;
- network access to official PyPI storage when the frozen wheel is absent;
- sufficient free space for the wheel, models, and ZIP bundle.

Confirm the checked-out commit before execution:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
git rev-parse HEAD
git status --short
```

The expected PR head for this revision is recorded in the pull request body.
Do not treat a different commit as evidence for that head.

## Standard execution

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

docs/mlforecast/run_runtime_certification.sh
```

The script can also be launched by absolute path from another directory. It
resolves the repository relative to its own location instead of the caller's
current Git repository.

## Keep the terminal open

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

set +e
docs/mlforecast/run_runtime_certification.sh
status=$?
printf '\nEXIT_STATUS=%s\n' "$status"
read -r -p 'Press Enter to close...'
exit "$status"
```

## Custom paths

```bash
docs/mlforecast/run_runtime_certification.sh \
  /absolute/path/mlforecast-1.1.0-py3-none-any.whl \
  /absolute/path/certification-runs \
  /absolute/path/certification-bundles
```

Disable automatic wheel download:

```bash
MLFORECAST_AUTO_DOWNLOAD=0 \
  docs/mlforecast/run_runtime_certification.sh
```

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Runtime status was `RUNTIME_CERTIFIED` and evidence ZIP creation passed. |
| `1` | Python certification failed, but the failure run was bundled successfully. |
| `2` | Prerequisite missing, such as wheel, `uv`, `sha256sum`, or `uv.lock`. |
| `3` | Wheel SHA-256 mismatch. Python execution did not start. |
| `4` | New Run ID detection was ambiguous or no new run directory was created. |
| `5` | Run evidence existed but manifest verification or ZIP creation failed. |

Do not convert codes `1` through `5` into success in outer scripts.

## Success verification

The command prints `RUN_ID`, `RUN_DIR`, `BUNDLE`, and `BUNDLE_SHA256`.
Verify the ZIP digest:

```bash
cd artifacts/mlforecast-runtime-bundles || exit 1
sha256sum -c <RUN_ID>.zip.sha256
```

Inspect the archive:

```bash
unzip -l <RUN_ID>.zip
unzip -p <RUN_ID>.zip \
  '<RUN_ID>/BUNDLE_VERIFICATION.json'
unzip -p <RUN_ID>.zip \
  '<RUN_ID>/RUNTIME_CERTIFICATION.json'
```

Formal success requires all of the following:

- shell exit code `0`;
- report status `RUNTIME_CERTIFIED`;
- ZIP SHA-256 verification passes;
- source status in `BUNDLE_VERIFICATION.json` is `RUNTIME_CERTIFIED`;
- Core and Auto model directories and prediction files are present.

## Failure handling

For exit code `1`, keep both the run directory and ZIP. The ZIP contains the
available failure report and artifacts. Do not delete or overwrite the source
run before root-cause analysis.

For exit code `3`, preserve the mismatched wheel separately and obtain a fresh
copy from the frozen official URL. Never bypass the digest check.

For exit code `4`, check for concurrent certification processes writing to the
same output root. Use separate output roots when parallel operator tests are
unavoidable.

For exit code `5`, inspect `ARTIFACT_MANIFEST.json`, `SHA256SUMS`, symlinks,
unexpected files, and missing model or prediction artifacts. Do not manually
edit a run directory and then claim it as certified.

## Re-run policy

Each run receives a unique timestamp-based Run ID. Bundles are never
silently overwritten. After correcting the root cause, execute a new run and
retain the previous failed evidence for comparison.

Do not repeatedly rerun GitHub Actions while the hosted runner has zero steps
and no logs. Treat that condition as infrastructure-blocked, not code success
or failure.

## Parallelism policy

This certification remains single-threaded by design. For formal prediction
campaigns, use eight outer workers under the project policy, retain inner
thread limits, preserve all seeds, and report mean, variance, and worst values.
