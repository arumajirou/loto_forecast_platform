#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform}"
cd "$ROOT"
command -v claude >/dev/null
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="artifacts/harness/claude-fix/${RUN_ID}"
mkdir -p "$OUT"
PROMPT_FILE="$OUT/prompt.md"

finish() {
  rc=$?
  set +e
  printf '%s\n' "$rc" > "$OUT/exit_code.txt"
  if [ "$rc" -eq 0 ]; then printf 'VERIFIED\n' > "$OUT/status.txt"; else printf 'FAILED\n' > "$OUT/status.txt"; fi
  (cd "$OUT" && find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  echo "CLAUDE_FIX_LOOP=$(cat "$OUT/status.txt")"
  echo "output=$OUT"
  exit "$rc"
}
trap finish EXIT

python3 scripts/harness/validate_scope.py "$ROOT" | tee "$OUT/scope-before.txt"
git status --short --branch | tee "$OUT/git-status-before.txt"
git diff --binary > "$OUT/before.patch"

cat > "$PROMPT_FILE" <<'PROMPT_EOF'
Implement and repair the harness until its bounded quality gates pass.
Read CLAUDE.md and CLAUDE.harness.md first. Work only in the documented harness scope. Do not push,
merge, reset, clean, delete artifacts, install system packages, or edit forecast/model evaluation logic.

Required loop:
1. inspect current failures
2. make the smallest bounded fix
3. run relevant tests
4. repeat up to the configured max turns
5. run final commands:
   uv run --extra harness --extra dev ruff check src/loto/harness tests/harness
   uv run --extra harness --extra dev mypy src/loto/harness
   uv run --extra harness --extra dev pytest -q tests/harness
6. report exact commands, exit codes, changed files, and remaining uncertainty

Never mark a model, engine, UI, or 64K context VERIFIED without live certification evidence.
PROMPT_EOF

set +e
claude -p \
  --model "${CLAUDE_MODEL:-sonnet}" \
  --max-turns "${CLAUDE_MAX_TURNS:-12}" \
  --output-format json \
  --no-session-persistence \
  --strict-mcp-config \
  --permission-mode dontAsk \
  --tools "Read,Grep,Glob,Edit,Write,Bash" \
  --allowedTools \
    "Read" "Grep" "Glob" "Edit" "Write" \
    "Bash(git status)" "Bash(git status *)" \
    "Bash(git diff)" "Bash(git diff *)" \
    "Bash(uv run pytest *)" "Bash(uv run ruff *)" "Bash(uv run mypy *)" \
  --disallowedTools \
    "mcp__*" \
    "Bash(git push *)" "Bash(git reset *)" "Bash(git clean *)" \
    "Bash(git checkout *)" "Bash(git switch *)" "Bash(git commit *)" \
    "Bash(rm *)" "Bash(sudo *)" "Bash(curl *)" "Bash(wget *)" \
  < "$PROMPT_FILE" | tee "$OUT/claude-fix.json"
CLAUDE_RC=${PIPESTATUS[0]}
set -e

set +e
python3 scripts/harness/validate_scope.py "$ROOT" 2>&1 | tee "$OUT/scope-after.txt"
SCOPE_RC=${PIPESTATUS[0]}
uv run --extra harness --extra dev ruff check src/loto/harness tests/harness 2>&1 | tee "$OUT/ruff.log"
RUFF_RC=${PIPESTATUS[0]}
uv run --extra harness --extra dev mypy src/loto/harness 2>&1 | tee "$OUT/mypy.log"
MYPY_RC=${PIPESTATUS[0]}
uv run --extra harness --extra dev pytest -q tests/harness 2>&1 | tee "$OUT/pytest.log"
PYTEST_RC=${PIPESTATUS[0]}
set -e

git diff --binary > "$OUT/after.patch"
git status --short --branch | tee "$OUT/git-status-after.txt"
cat > "$OUT/result.env" <<RESULT
CLAUDE_RC=$CLAUDE_RC
SCOPE_RC=$SCOPE_RC
RUFF_RC=$RUFF_RC
MYPY_RC=$MYPY_RC
PYTEST_RC=$PYTEST_RC
RESULT

if [ "$CLAUDE_RC" -eq 0 ] \
  && [ "$SCOPE_RC" -eq 0 ] \
  && [ "$RUFF_RC" -eq 0 ] \
  && [ "$MYPY_RC" -eq 0 ] \
  && [ "$PYTEST_RC" -eq 0 ]; then
  exit 0
fi
exit 1
