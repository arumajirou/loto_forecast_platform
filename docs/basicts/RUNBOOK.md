# BasicTS provider runbook

## Resolve the isolated environment

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="/absolute/path/to/logs/basicts-${RUN_ID}"
mkdir -p "$LOG_DIR"

set -o pipefail
uv lock --project environments/basicts-py310 \
  2>&1 | tee "$LOG_DIR/uv-lock.log"
LOCK_EXIT="${PIPESTATUS[0]}"
printf '%s\n' "$LOCK_EXIT" > "$LOG_DIR/uv-lock.exit-code"
```

Review dependency changes before committing the generated lockfile.

## Validate the provider contract

Convert the example YAML to JSON with a trusted local tool, use an absolute artifact path, then run:

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
export PYTHONPATH="$PWD/src"
REQUEST="/absolute/path/to/request.json"
RESPONSE="/absolute/path/to/response.json"
LOG="/absolute/path/to/basicts-provider.log"

set -o pipefail
uv run --project environments/basicts-py310 \
  python scripts/run_basicts_provider.py \
  --request "$REQUEST" \
  --response "$RESPONSE" \
  2>&1 | tee "$LOG"
EXIT_CODE="${PIPESTATUS[0]}"
printf '%s\n' "$EXIT_CODE" > "${LOG}.exit-code"
printf 'Press Enter to close...'
read -r _
```

## Required promotion evidence

Before any accuracy campaign, verify package identity, config allowlist, chronological split,
Train-only scaler scope, finite output, expected shape, save/load/re-predict behavior, and every
SHA-256. A skipped runtime test is not a pass.
