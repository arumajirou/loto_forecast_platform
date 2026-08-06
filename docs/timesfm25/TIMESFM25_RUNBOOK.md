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

## Create the target-host request

Copy the example, replace the timestamp-like placeholder with a unique Run ID, and
set `snapshot_path` to the absolute pinned snapshot directory.

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

## Generate and verify the isolated lockfile

When `environments/timesfm25-pytorch/uv.lock` does not exist, create it explicitly:

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

`--generate-lock` is the only preparation step permitted to resolve packages. The
subsequent checks use `uv lock --check --offline` and
`uv run --locked --offline`. When a lockfile already exists, omit
`--generate-lock`; the script fails if the lockfile is missing, stale, malformed,
or contains different pinned versions.

The preflight also verifies:

```text
repo_id and revision match the backend manifest
pyproject.toml exact TimesFM/Torch/Hugging Face Hub pins
uv.lock exact locked versions
absolute local snapshot path
valid config.json
exactly one model.safetensors
model.safetensors SHA-256
runtime import versions
PyTorch CUDA availability and device count
nvidia-smi availability and query success
offline environment enforcement
```

Do not continue unless the generated report contains `"status": "PASS"`.

## Runtime certification

For a long GPU run, use `tmux` so the process and evidence survive terminal closure:

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail

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
     2>&1 | tee '$CONSOLE_LOG'; \
   rc=\${PIPESTATUS[0]}; \
   printf 'EXIT_CODE=%s\n' \"\$rc\" | tee -a '$CONSOLE_LOG'; \
   printf 'Enterキーで終了します...'; read -r _"

printf 'TMUX_SESSION=%s\n' "$SESSION"
printf 'CONSOLE_LOG=%s\n' "$CONSOLE_LOG"
printf 'ATTACH_COMMAND=tmux attach -t %s\n' "$SESSION"
```

The launcher independently repeats the preflight before starting the provider. A
failed preflight creates and seals a failure bundle but does not start model loading
or inference.

The immutable run directory records:

```text
provider_request.json
preflight.json
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
0 = VERIFIED_CPU or VERIFIED_GPU
2 = PARTIALLY_VERIFIED_GPU
1 = preflight, provider, request, bundle, or orchestration failure
```

`PARTIALLY_VERIFIED_GPU` is expected for the native API while mean and quantile
outputs are CPU NumPy arrays. It must not be reported as strict GPU certification.

## Verify a completed evidence directory

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

printf 'Enterキーで終了します...'
read -r _
```
