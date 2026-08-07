#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform}"
cd "$ROOT"
command -v claude >/dev/null
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="artifacts/harness/claude-review/${RUN_ID}"
mkdir -p "$OUT"
PROMPT_FILE="$OUT/prompt.md"

finish() {
  rc=$?
  set +e
  printf '%s\n' "$rc" > "$OUT/exit_code.txt"
  if [ "$rc" -eq 0 ]; then printf 'VERIFIED\n' > "$OUT/status.txt"; else printf 'FAILED\n' > "$OUT/status.txt"; fi
  (cd "$OUT" && find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  echo "CLAUDE_REVIEW=$(cat "$OUT/status.txt")"
  echo "output=$OUT"
  exit "$rc"
}
trap finish EXIT

python3 scripts/harness/validate_scope.py "$ROOT" | tee "$OUT/scope-before.txt"
git status --short --branch | tee "$OUT/git-status-before.txt"
git diff --binary > "$OUT/before.patch"

cat > "$PROMPT_FILE" <<'PROMPT'
Review the harness implementation only. Do not edit files.

Scope:
- src/loto/harness
- tests/harness
- configs/harness
- deploy/systemd/user/loto-harness-*.service
- deploy/prometheus
- deploy/grafana
- deploy/harness-stack.compose.yml
- scripts/harness
- docs/harness
- pyproject.toml and Claude harness instruction imports

Check correctness, error handling, shell/path safety, API compatibility, model load/unload,
64K safety, protected-context loss, loop stop/rollback behavior, append-only memory semantics,
observability cardinality, dependency compatibility, and missing tests.

Return JSON with keys verdict, blocking_findings, non_blocking_findings, recommended_tests,
commands_run, exit_codes, and exact_file_locations. Never claim a test was run without evidence.
PROMPT

set +e
claude -p \
  --model "${CLAUDE_MODEL:-sonnet}" \
  --max-turns "${CLAUDE_MAX_TURNS:-8}" \
  --output-format json \
  --no-session-persistence \
  --strict-mcp-config \
  --permission-mode dontAsk \
  --tools "Read,Grep,Glob,Bash" \
  --allowedTools \
    "Read" "Grep" "Glob" \
    "Bash(git status)" "Bash(git status *)" \
    "Bash(git diff)" "Bash(git diff *)" \
    "Bash(uv run pytest *)" "Bash(uv run ruff *)" "Bash(uv run mypy *)" \
  --disallowedTools \
    "Edit" "Write" "mcp__*" \
    "Bash(git push *)" "Bash(git reset *)" "Bash(git clean *)" \
    "Bash(rm *)" "Bash(sudo *)" \
  < "$PROMPT_FILE" | tee "$OUT/claude-review.json"
CLAUDE_RC=${PIPESTATUS[0]}
set -e

python3 scripts/harness/validate_scope.py "$ROOT" | tee "$OUT/scope-after.txt"
git diff --binary > "$OUT/after.patch"
printf 'CLAUDE_RC=%s\n' "$CLAUDE_RC" > "$OUT/result.env"
exit "$CLAUDE_RC"
