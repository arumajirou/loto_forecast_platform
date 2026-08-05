# TimesFM 2.5 Runbook

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
set -Eeuo pipefail
RUN_ID="timesfm25-$(date +%Y%m%d-%H%M%S)"
LOG="artifacts/timesfm25/${RUN_ID}/run.log"
mkdir -p "$(dirname "$LOG")"
trap 'rc=$?; printf "EXIT_CODE=%s\n" "$rc" | tee -a "$LOG"; printf "Press Enter to close..."; read -r _' EXIT
uv run pytest tests/adapters/timesfm25 tests/timesfm25_campaign 2>&1 | tee "$LOG"
```

The real provider must be run with a pre-populated pinned Hugging Face snapshot and `local_files_only=true`.
