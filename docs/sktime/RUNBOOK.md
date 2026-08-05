# sktime P0 target-host certification runbook

## Status boundary

```text
IMPLEMENTATION=EXECUTED
LOCAL_STATIC_SCRIPT_CHECK=VERIFIED_BY_AUTHORING_AGENT
TARGET_KUBUNTU_EXECUTION=EXECUTION_PENDING
ISOLATED_UV_LOCK=EXECUTION_PENDING
REAL_FORECASTER_COUNT=EXECUTION_PENDING
REAL_NAIVE_SAVE_LOAD=EXECUTION_PENDING
```

This runbook executes the isolated `sktime==1.0.1` P0 lane. It does not modify the root
`pyproject.toml`, root `uv.lock`, common worker, common catalog, or GitHub Actions workflow.

## Preconditions

- repository path: `/mnt/e/env/ts/loto_forecast_platform`;
- branch: `agent/sktime-forecasting-contract-v1`;
- `uv`, Git, Python 3.13, `sha256sum`, and `tmux` available;
- package registry can resolve the isolated environment;
- no unrelated local change should be staged or overwritten.

Inspect the checkout before execution:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
```

Fetch and switch to the Draft PR branch when needed:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin \
  agent/sktime-forecasting-contract-v1

git switch \
  agent/sktime-forecasting-contract-v1

git pull --ff-only
```

Do not use `git reset --hard`, force push, or automatic merge.

## Recommended tmux execution

The launcher refuses to replace an already running session.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

bash scripts/start_sktime_p0_certification_tmux.sh
```

Expected launch output:

```text
SKTIME_TMUX_STATUS=STARTED
session=sktime-p0-certification
```

Attach to the session:

```bash
tmux attach -t sktime-p0-certification
```

The terminal stop key may be configured as `Ctrl+Q` in this environment. Do not assume
`Ctrl+C` is the only stop key.

## Foreground execution

Use this only when an attached terminal is acceptable. The script waits for Enter before
closing unless `SKTIME_NO_PAUSE=1` is set.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

bash scripts/run_sktime_p0_certification.sh
```

## What the runner executes

1. records Git HEAD, branch, remote, kernel, UTC time, and `uv` version;
2. resolves `environments/sktime-core-py313/uv.lock`;
3. records the lock SHA-256;
4. performs `uv sync --frozen` in the isolated environment;
5. verifies exact `sktime==1.0.1` and dependency versions;
6. runs Ruff format check and lint on sktime-owned paths;
7. runs Python `compileall`;
8. runs focused `tests/sktime_campaign` tests;
9. executes dynamic `all_estimators("forecaster")` inventory;
10. executes NaiveForecaster fit, predict, ZIP save, load, and re-predict;
11. verifies provider manifests and nested SHA-256 files;
12. writes a top-level `VERIFICATION_REPORT.json`, manifest, and portable `SHA256SUMS`;
13. records the final process exit code.

The sequence is intentionally bounded and sequential. It is a dependency and contract
certification, not an eight-way model-training campaign.

## Artifact location

Each execution writes under:

```text
/mnt/e/env/ts/loto_forecast_platform/artifacts/sktime-p0/<run-id>/
```

Important files:

```text
RUN_METADATA.txt
UV_LOCK_SHA256
environment.json
focused-pytest.log
inventory/
naive-smoke/
VERIFICATION_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
exit_code.txt
logs/certification.log
```

Logs and `exit_code.txt` remain audit evidence but are excluded from the stable portable
SHA seal because the main log is still being appended while finalization runs and the exit
code is written by the EXIT trap. The manifest records this exclusion explicitly.

## Monitoring

Find the newest run:

```bash
ROOT=/mnt/e/env/ts/loto_forecast_platform

RUN_DIR="$(
  find "${ROOT}/artifacts/sktime-p0" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -printf '%T@ %p\n' \
  | sort -nr \
  | head -n 1 \
  | cut -d' ' -f2-
)"

printf 'run_dir=%s\n' "${RUN_DIR}"
tail -n 100 -f \
  "${RUN_DIR}/logs/certification.log"
```

Check whether the tmux session still exists:

```bash
tmux has-session \
  -t sktime-p0-certification \
  && echo ACTIVE \
  || echo FINISHED
```

## Success verification

```bash
ROOT=/mnt/e/env/ts/loto_forecast_platform

RUN_DIR="$(
  find "${ROOT}/artifacts/sktime-p0" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -printf '%T@ %p\n' \
  | sort -nr \
  | head -n 1 \
  | cut -d' ' -f2-
)"

cat "${RUN_DIR}/exit_code.txt"
cat "${RUN_DIR}/VERIFICATION_REPORT.json"

(
  cd "${RUN_DIR}" || exit 1
  sha256sum -c SHA256SUMS
)
```

Formal P0 success requires:

```text
exit_code.txt = 0
VERIFICATION_REPORT.status = PASS
dynamic_inventory = VERIFIED
naive_fit_predict_save_load = VERIFIED
inventory discovered count > 0
actual_sktime_version = 1.0.1
all portable SHA-256 checks = OK
```

## Review the generated lock

`uv lock` creates or updates the isolated lock only:

```text
environments/sktime-core-py313/uv.lock
```

Review before committing:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git status --short
git diff -- \
  environments/sktime-core-py313/pyproject.toml \
  environments/sktime-core-py313/uv.lock

uv lock --check \
  --project environments/sktime-core-py313
```

Do not stage unrelated files. The generated `artifacts/` directory should remain outside
the source commit unless an explicitly reviewed evidence policy says otherwise.

## Failure handling

A nonzero exit is not runtime success. Preserve the entire run directory and inspect:

```text
exit_code.txt
logs/certification.log
inventory/response.json
naive-smoke/response.json
git-status-before.txt
git-status-after.txt
```

Typical classifications:

- dependency resolution failure: `BLOCKED_PACKAGE_RESOLUTION`;
- exact version mismatch: `FAILED_VERSION_CONTRACT`;
- focused test failure: `FAILED_LOCAL_TEST`;
- inventory failure: `FAILED_INVENTORY_RUNTIME`;
- Naive fit or save/load failure: `FAILED_NAIVE_RUNTIME`;
- SHA or manifest mismatch: `FAILED_ARTIFACT_INTEGRITY`.

Do not replace a failed Run ID. Correct the cause and execute a new Run ID.

## GitHub handoff

After a successful target-host run, add the resolved isolated `uv.lock` to Draft PR #52
only after reviewing its diff. Attach a concise PR comment containing:

- run directory;
- Git HEAD;
- isolated lock SHA-256;
- discovered/importable/core/optional counts;
- focused pytest result;
- Naive save/load result;
- top-level SHA verification result;
- remaining certification boundaries.

Do not mark the PR ready for review or merge solely because the Naive smoke passed. Full
repository CI and later sktime tracks remain separate gates.
