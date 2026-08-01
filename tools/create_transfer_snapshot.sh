#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${1:-$PWD}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="${2:-$(dirname "$REPO")/$(basename "$REPO")-transfer-${RUN_ID}.tar.zst}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/repository" "$STAGE/git-evidence"
cd "$REPO"
git status --short > "$STAGE/git-evidence/status-short.txt"
git diff > "$STAGE/git-evidence/working-tree.diff"
git diff --cached > "$STAGE/git-evidence/index.diff"
git ls-files > "$STAGE/git-evidence/tracked-files.txt"
git ls-files --others --exclude-standard > "$STAGE/git-evidence/untracked-files.txt"
# Root-anchored excludes: never exclude src/loto/data or other source packages.
rsync -a \
  --exclude='/.git/' \
  --exclude='/.venv/' \
  --exclude='/.venv-*/' \
  --exclude='/.pytest_cache/' \
  --exclude='/.ruff_cache/' \
  --exclude='/**/__pycache__/' \
  --exclude='/runs/' \
  --exclude='/audit/' \
  --exclude='/data/' \
  --exclude='/artifacts/' \
  --exclude='/mlruns/' \
  --exclude='/*.sqlite3' \
  --exclude='*.pyc' \
  "$REPO/" "$STAGE/repository/"
(cd "$STAGE/repository" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$STAGE/git-evidence/snapshot-files.sha256"
tar --zstd -cf "$OUT" -C "$STAGE" .
sha256sum "$OUT" > "$OUT.sha256"
printf '%s\n' "$OUT"
