# Chronos-2 Runbook

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail
RUN_ID="chronos2-$(date +%Y%m%d-%H%M%S)"
LOG_DIR="/absolute/path/to/logs/${RUN_ID}"
mkdir -p "$LOG_DIR"
trap 'rc=$?; printf "%s\n" "$rc" >"$LOG_DIR/exit_code"; printf "EXIT_CODE=%s\n" "$rc"; read -r -p "Press Enter to close..." _' EXIT

uv run --project environments/chronos2-py313 \
  python scripts/run_chronos2_provider.py \
  --request configs/chronos2_campaign/provider_v2.example.json \
  --response "$LOG_DIR/response.json" \
  2>&1 | tee "$LOG_DIR/provider.log"
```

For long GPU runs, execute this command inside a named `tmux` session or a systemd user service. Stop keys vary by terminal; do not assume Ctrl+C when the terminal reports Ctrl+Q.
