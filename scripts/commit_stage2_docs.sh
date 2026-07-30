#!/usr/bin/env bash
set -euo pipefail

PUSH=0

if [ "${1:-}" = "--push" ]; then
  PUSH=1
elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--push]" >&2
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

REQUIRED=(
  ".gitignore"
  "docs/verification/stage2-validation-report-2026-07-31.md"
  "docs/operations/gpu-campaign-stage2-runbook.md"
  "docs/architecture/model-parameter-verification.md"
  "scripts/commit_stage2_docs.sh"
)

for path in "${REQUIRED[@]}"; do
  if [ ! -e "$path" ]; then
    echo "ERROR: 必須ファイルがありません: $path" >&2
    exit 1
  fi
done

git add -- "${REQUIRED[@]}"

echo "===== STAGED FILES ====="
git diff --cached --name-status

FORBIDDEN_REGEX='^(runs/|logs/)|\.(ckpt|pt|pth|onnx|joblib|pkl|pickle)$'

if git diff --cached --name-only | grep -E "$FORBIDDEN_REGEX"; then
  echo "ERROR: 実験成果物がステージされています。" >&2
  exit 1
fi

large=0

while IFS= read -r path; do
  [ -f "$path" ] || continue
  size="$(stat -c '%s' "$path")"
  if [ "$size" -gt 10485760 ]; then
    echo "ERROR: 10MiB超のステージファイル: $size $path" >&2
    large=1
  fi
done < <(git diff --cached --name-only)

if [ "$large" -ne 0 ]; then
  exit 1
fi

if git diff --cached --quiet; then
  echo "コミット対象の変更はありません。"
else
  git commit -m "document Stage 2 validation and campaign operations"
fi

git show --stat --oneline --decorate HEAD

if [ "$PUSH" -eq 1 ]; then
  branch="$(git branch --show-current)"
  if [ -z "$branch" ]; then
    echo "ERROR: 現在のブランチを判定できません。" >&2
    exit 1
  fi

  git push -u origin "$branch"
  echo "PUSH=PASS"
  echo "BRANCH=$branch"
else
  echo "PUSH=SKIPPED"
  echo "pushする場合:"
  echo "  $0 --push"
fi
