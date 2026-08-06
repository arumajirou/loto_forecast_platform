# TimesFM 2.5 Runbook

## Focused tests

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail

RUN_ID="timesfm25-tests-$(date +%Y%m%d-%H%M%S)"
LOG_ROOT="$HOME/Downloads/timesfm25-tests"
RUN_DIR="${LOG_ROOT}/${RUN_ID}"
mkdir -p "$RUN_DIR"
LOG="${RUN_DIR}/run.log"
EXIT_FILE="${RUN_DIR}/exit_code.txt"

cleanup() {
  rc=$?
  printf '%s\n' "$rc" > "$EXIT_FILE"
  printf 'EXIT_CODE=%s\n' "$rc" | tee -a "$LOG"
  printf 'RUN_DIR=%s\n' "$RUN_DIR" | tee -a "$LOG"
  printf 'Enterキーで終了します...'
  read -r _
}
trap cleanup EXIT

uv run pytest \
  tests/adapters/timesfm25 \
  tests/timesfm25_campaign \
  2>&1 | tee "$LOG"
```

## Recommended target-host operator workflow

The operator command performs request creation, preflight, tmux launch, status
inspection, bundle verification, and deterministic ZIP finalization. Use a new Run
ID for every attempt.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

RUN_ID="timesfm25-native-$(date -u +%Y%m%dT%H%M%SZ)"
SNAPSHOT="/absolute/path/to/pinned/google-timesfm-2.5-200m-pytorch-snapshot"

uv run python scripts/run_timesfm25_target_host.py launch \
  --run-id "$RUN_ID" \
  --snapshot "$SNAPSHOT" \
  --generate-lock \
  --preflight-timeout 600 \
  --timeout 3600

printf 'RUN_ID=%s\n' "$RUN_ID"
printf 'STATUS_COMMAND=uv run python scripts/run_timesfm25_target_host.py status --run-id %s\n' \
  "$RUN_ID"
printf 'Enterキーで終了します...'
read -r _
```

Use `--generate-lock` only when creating or intentionally refreshing the isolated
`environments/timesfm25-pytorch/uv.lock`. Omit it on later runs so the existing lock
must pass the offline consistency checks.

Check progress without modifying the runtime bundle:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
RUN_ID="<the same run id>"

uv run python scripts/run_timesfm25_target_host.py status \
  --run-id "$RUN_ID"

printf 'ATTACH_COMMAND=tmux attach -t tfm25-%s\n' \
  "${RUN_ID//_/-}"
printf 'Enterキーで終了します...'
read -r _
```

After the tmux session finishes, verify and archive the sealed evidence:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
RUN_ID="<the same run id>"

uv run python scripts/run_timesfm25_target_host.py finalize \
  --run-id "$RUN_ID"

printf 'Enterキーで終了します...'
read -r _
```

Finalization exit codes:

```text
0 = COMPLETED; verified CPU or strict verified GPU bundle archived
2 = PARTIAL; partial GPU evidence bundle archived
3 = RUNNING; tmux session is still active and no archive was created
1 = failed, corrupt, incomplete, unsealed, or invalid bundle
```

The operator creates control files under:

```text
artifacts/timesfm25/operator/<run_id>/
```

The immutable runtime evidence remains under:

```text
artifacts/timesfm25/runtime-certification/<run_id>/
```

Verified archives and SHA-256 sidecars are written outside the sealed runtime bundle:

```text
artifacts/timesfm25/runtime-archives/<run_id>.zip
artifacts/timesfm25/runtime-archives/<run_id>.zip.sha256
```

`--foreground` is available for diagnosis when tmux cannot be used. Detached tmux is
the normal target-host mode.

## Manual target-host request and preflight

Copy the example, replace the placeholder with a unique Run ID, and set
`snapshot_path` to the absolute pinned snapshot directory.

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail

REQUEST="$HOME/Downloads/timesfm25-provider-request.json"
cp configs/timesfm25_campaign/runtime_request.example.json "$REQUEST"

printf 'REQUEST=%s\n' "$REQUEST"
printf 'Edit run_id, history, geometry, and snapshot_path before continuing.\n'
printf 'Enterキーで終了します...'
read -r _
```

The preflight requires an absolute snapshot path containing exactly one
`model.safetensors` plus a valid `config.json`. The weight SHA-256 must match the
backend manifest.

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail

REQUEST="$HOME/Downloads/timesfm25-provider-request.json"
PREFLIGHT="$HOME/Downloads/timesfm25-preflight-$(date +%Y%m%d-%H%M%S).json"

uv run python scripts/prepare_timesfm25_runtime.py \
  --request "$REQUEST" \
  --environment environments/timesfm25-pytorch \
  --manifest configs/timesfm25_campaign/model_manifest.json \
  --output "$PREFLIGHT" \
  --generate-lock \
  --timeout 600

printf 'PREFLIGHT=%s\n' "$PREFLIGHT"
printf 'Enterキーで終了します...'
read -r _
```

Do not continue unless the generated report contains `"status": "PASS"`.

## Manual runtime certification

The operator CLI is preferred. The lower-level launcher remains available:

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -EEo pipefail

REQUEST="$HOME/Downloads/timesfm25-provider-request.json"
SESSION="timesfm25-cert-$(date +%Y%m%d-%H%M%S)"
LOG_ROOT="$HOME/Downloads/timesfm25-launcher"
mkdir -p "$LOG_ROOT"
CONSOLE_LOG="${LOG_ROOT}/${SESSION}.log"

tmux new-session -d -s "$SESSION" \
  "cd '$PWD' && \
   uv run python scripts/run_timesfm25_runtime_certification.py \
     --request '$REQUEST' \
     --environment environments/timesfm25-pytorch \
     --output-root artifacts/timesfm25/runtime-certification \
     --preflight-timeout 600 \
     --timeout 3600 \
     2>&1 | tee '$CONSOLE_LOG'"

printf 'TMUX_SESSION=%s\n' "$SESSION"
printf 'CONSOLE_LOG=%s\n' "$CONSOLE_LOG"
printf 'ATTACH_COMMAND=tmux attach -t %s\n' "$SESSION"
```

The launcher independently repeats preflight before starting the provider. A
failed preflight creates and seals a failure bundle but does not start model loading or
inference.

Runtime exit codes:

```text
0 = VERIFIED_CPE or VERIFIED_GPU
2 = PARTIALLY_VERIFIED_GPU
1 = preflight, provider, request, bundle, or orchestration failure
```

`PARTIALLY_VERIFIED_GPU` is expected for the native API while mean and quantile
outputs are CPU NumPy arrays. It must not be reported as strict GPU certification.
