# MLForecast 1.1.0 Runtime Certification

## Current status

`PYPI_DIGEST_VERIFIED / INSTALLED_RUNTIME_EXECUTION_PENDING`

The official PyPI release metadata identifies the frozen wheel as:

- filename: `mlforecast-1.1.0-py3-none-any.whl`
- upload time: `2026-07-10T00:52:25.071033Z`
- size: `261702` bytes
- SHA-256: `0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748`

The wheel URL, digest, version, tag, and upstream commit are frozen. This does
not by itself certify an installed runtime. Formal success requires the exact
wheel to execute through the dedicated certification path.

## One-command operation

Run from any directory:

```bash
/mnt/e/env/ts/loto_forecast_platform/docs/mlforecast/run_runtime_certification.sh
```

The wrapper resolves the repository from its own location. When the wheel is
missing, it downloads the exact frozen file from the official PyPI storage URL
to `artifacts/mlforecast-wheel/`. Automatic download can be disabled with:

```bash
MLFORECAST_AUTO_DOWNLOAD=0 \
  docs/mlforecast/run_runtime_certification.sh
```

Optional positional arguments are:

```text
1: wheel path
2: certification output root
3: bundle output root
```

## Execution sequence

1. require `uv`, `sha256sum`, `uv.lock`, and the repository source tree;
2. download the exact wheel when it is absent and download is enabled;
3. verify wheel SHA-256 before Python execution;
4. set OMP, MKL, OpenBLAS, and NumExpr thread variables to exactly `1`;
5. run `uv run --frozen --with <local-wheel>` so the verified wheel is
   actually present in the ephemeral runtime without changing `uv.lock`;
6. execute Core Ridge and AutoRidge certification;
7. detect exactly one newly created Run ID;
8. verify `ARTIFACT_MANIFEST.json` and `SHA256SUMS` against every file;
9. create a deterministic ZIP and a separate ZIP SHA-256 file;
10. return the certification exit status after evidence bundling.

## Pass criteria

Formal status is `RUNTIME_CERTIFIED` only when all of the following pass:

1. wheel bytes match the frozen SHA-256;
2. wheel `METADATA` reports `Name: mlforecast` and `Version: 1.1.0`;
3. installed distribution reports exactly version 1.1.0;
4. all four thread-control variables equal `1`;
5. Core Ridge fits and produces two finite one-step predictions;
6. Core Ridge save/load preserves prediction keys and values;
7. every requested seeded AutoRidge Optuna trial completes;
8. AutoRidge best objective and predictions are finite;
9. AutoRidge save/load preserves prediction keys and values;
10. process, CPU, package, Git, source-hash, prediction, trial, model,
    manifest, and portable hash evidence is written.

A skipped test, missing or mismatched wheel, version mismatch, thread-contract
violation, incomplete trial set, duplicate or changed keys, non-finite output,
shape mismatch, or save/load mismatch is failure.

## Expected run artifacts

```text
RUNTIME_CERTIFICATION.json
synthetic_panel.csv
inputs/mlforecast-1.1.0-py3-none-any.whl
core_ridge_predictions.csv
auto_ridge_predictions.csv
auto_ridge_trials.csv
models/core-ridge/**
models/auto-ridge/**
ARTIFACT_MANIFEST.json
SHA256SUMS
```

A failed certification still writes its available evidence, manifest, and
hashes whenever the Python certifier starts successfully.

## Deterministic evidence bundle

The bundler rejects unsafe paths, symlinks, duplicate manifest entries,
manifest or checksum disagreement, unexpected extra files, and missing
success artifacts. ZIP entries are sorted and use a fixed timestamp, so the
same source run produces the same ZIP bytes.

```text
artifacts/mlforecast-runtime-bundles/<RUN_ID>.zip
artifacts/mlforecast-runtime-bundles/<RUN_ID>.zip.sha256
```

The archive includes `BUNDLE_VERIFICATION.json`, the source report, the exact
wheel, model bundles, predictions, trials, manifest, and checksums.

## Parallelism boundary

Runtime certification is intentionally one process and one thread. It is a
reproducibility and lifecycle gate, not an accuracy campaign. Formal model
experiments may use the project-standard eight outer workers, while limiting
inner threads and GPU concurrency separately.

## Environment boundary

The current conversation execution environment cannot resolve the PyPI file
host, so the official wheel bytes could not be executed here. Repository tests
validate the certification and bundling implementation, but installed-runtime
success must be produced in an environment with the frozen wheel and its
runtime dependencies.
