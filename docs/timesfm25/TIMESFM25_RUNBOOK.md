# TimesFM 2.5 Runbook

## Focused tests

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail

RUN_ID="timesfm25-tests-$(date +%Y%m%d-%H%M%S)"
LOG_ROOT="/absolute/path/to/logs/timesfm25"
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

## Runtime certification

Prepare a schema-v2 request with a unique `run_id`, the exact pinned repository
revision, `local_files_only=true`, and a pre-populated snapshot. Raw model data is
never downloaded by the certification launcher.

For a long GPU run, use `tmux` so the process and evidence survive terminal closure:

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail

REQUEST="/absolute/path/to/provider_request.json"
SESSION="timesfm25-cert-$(date +%Y%m%d-%H%M%S)"
LOG_ROOT="/absolute/path/to/logs/timesfm25-launcher"
mkdir -p "$LOG_ROOT"
CONSOLE_LOG="${LOG_ROOT}/${SESSION}.log"

tmux new-session -d -s "$SESSION" \
  "cd '$PWD' && \
   uv run python scripts/run_timesfm25_runtime_certification.py \
     --request '$REQUEST' \
     --environment environments/timesfm25-pytorch \
     --output-root artifacts/timesfm25/runtime-certification \
     --timeout 3600 \
     2>&1 | tee '$CONSOLE_LOG'; \
   rc=\${PIPESTATUS[0]}; \
   printf 'EXIT_CODE=%s\n' \"\$rc\" | tee -a '$CONSOLE_LOG'; \
   printf 'Enterキーで終了します...'; read -r _"

printf 'TMUX_SESSION=%s\n' "$SESSION"
printf 'CONSOLE_LOG=%s\n' "$CONSOLE_LOG"
printf 'ATTACH_COMMAND=tmux attach -t %s\n' "$SESSION"
```

The launcher creates an immutable run directory named after `request.run_id`. It
refuses to overwrite an existing directory and records:

```text
provider_request.json
provider_response.json
command.json
environment.json
provider.stdout.log
provider.stderr.log
provider_exit_code.txt
nvidia_process_samples.csv
nvidia_process_monitor.stderr.log
runtime_certification.json
status.txt
SHA256SUMS
```

Exit codes:

```text
0 = VERIFIEED_CPU or VERIFIED_GPU
2 = PARTIALLY_VERIFIED_GPU
1 = provider, request, bundle, or orchestration failure
```

`PARTIALLY_VERIFIED_GPU` is expected for the native API while mean and quantile
outputs are CPU NumPy arrays. It must not be reported as strict GPU certification.

Verify a completed evidence directory:

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
RUN_DIR="/absolute/path/to/artifacts/timesfm25/runtime-certification/<run_id>"

uv run python - "$RUN_DIR" <<'PY'
from pathlib import Path
import sys

from loto.timesfm25_campaign.certification_bundle import verify_sha256_manifest

run_dir = Path(sys.argv[1])
ok, failures = verify_sha256_manifest(run_dir)
print(f"SHA256_VERIFY={'PASS' if ok else 'FAIL'}")
for failure in failures:
    print(f"FAILURE={failure}")
raise SystemExit(0 if ok else 1)
PY

printf 'Enterソーで終了します...'
read -r _
```
