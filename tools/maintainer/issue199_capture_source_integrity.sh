#!/usr/bin/env bash
set -Eeuo pipefail

REPO="arumajirou/loto_forecast_platform"
TARGET_BRANCH="fix/ruff-format-normalization-v1"
TARGET_FILE="src/loto/auto_campaign/prospective_registry_reconciliation_expected.py"
ISSUE=199

for cmd in git gh python3 sha256sum; do
  command -v "$cmd" >/dev/null || {
    echo "STOP_REASON=MISSING_TOOL_$cmd"
    exit 10
  }
done

gh auth status -h github.com >/dev/null
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]]; then
  echo "STOP_REASON=WRONG_BRANCH"
  echo "EXPECTED_BRANCH=$TARGET_BRANCH"
  echo "CURRENT_BRANCH=$CURRENT_BRANCH"
  exit 11
fi

if [[ -n "$(git status --porcelain=v1)" ]]; then
  echo "STOP_REASON=WORKTREE_NOT_CLEAN"
  git status --short
  exit 12
fi

RUN_ID="ghmaint-$(date -u +%Y%m%d-%H%M%S)-issue199-source-integrity"
TMP_ROOT="$(mktemp -d -t loto-issue199-XXXXXX)"
CAPTURE_DIR="$TMP_ROOT/capture"
EVIDENCE_WT="$TMP_ROOT/evidence-worktree"
mkdir -p "$CAPTURE_DIR"

cleanup() {
  set +e
  git worktree remove --force "$EVIDENCE_WT" >/dev/null 2>&1 || true
  rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "RUN_ID=$RUN_ID"
echo "ROOT=$ROOT"

git fetch --prune origin main "$TARGET_BRANCH"
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/$TARGET_BRANCH")"
MAIN_SHA="$(git rev-parse origin/main)"

printf 'LOCAL_SHA=%s\nREMOTE_SHA=%s\nMAIN_SHA=%s\n' "$LOCAL_SHA" "$REMOTE_SHA" "$MAIN_SHA"
if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
  echo "STOP_REASON=TARGET_BRANCH_NOT_UP_TO_DATE"
  exit 13
fi

{
  echo "RUN_ID=$RUN_ID"
  echo "REPOSITORY=$REPO"
  echo "TARGET_BRANCH=$TARGET_BRANCH"
  echo "TARGET_FILE=$TARGET_FILE"
  echo "LOCAL_SHA=$LOCAL_SHA"
  echo "REMOTE_SHA=$REMOTE_SHA"
  echo "MAIN_SHA=$MAIN_SHA"
  echo "UNAME=$(uname -a 2>/dev/null || true)"
  echo "PYTHON=$(python3 --version 2>&1)"
  echo "GH=$(gh --version | head -n 1)"
} > "$CAPTURE_DIR/environment.env"

python3 - "$TARGET_FILE" "$CAPTURE_DIR/source-integrity.txt" <<'PY'
from __future__ import annotations

import hashlib
import py_compile
import sys
from pathlib import Path

source = Path(sys.argv[1])
out = Path(sys.argv[2])
data = source.read_bytes()

records = [
    "SOURCE_INTEGRITY_CAPTURE_VERSION=1",
    f"TARGET_FILE={source.as_posix()}",
    f"SIZE_BYTES={len(data)}",
    f"SHA256={hashlib.sha256(data).hexdigest()}",
    f"UTF8_BOM={data.startswith(bytes.fromhex('efbbbf'))}",
    f"UTF16_LE_BOM={data.startswith(bytes.fromhex('fffe'))}",
    f"UTF16_BE_BOM={data.startswith(bytes.fromhex('feff'))}",
    f"NUL_BYTE_COUNT={data.count(bytes([0]))}",
]

errors: list[tuple[int, int, str]] = []
cursor = 0
while cursor < len(data):
    try:
        data[cursor:].decode("utf-8")
        break
    except UnicodeDecodeError as exc:
        start = cursor + exc.start
        end = cursor + exc.end
        errors.append((start, end, exc.reason))
        cursor = end if end > start else start + 1
        if len(errors) >= 100:
            break

records.append(f"UTF8_DECODE_ERROR_COUNT_CAPPED={len(errors)}")
for i, (start, end, reason) in enumerate(errors, start=1):
    line = data.count(b"\n", 0, start) + 1
    previous_newline = data.rfind(b"\n", 0, start)
    column = start + 1 if previous_newline < 0 else start - previous_newline
    lo = max(0, start - 32)
    hi = min(len(data), end + 32)
    window = data[lo:hi]
    records.extend(
        [
            f"ERROR_{i}_START={start}",
            f"ERROR_{i}_END={end}",
            f"ERROR_{i}_LINE={line}",
            f"ERROR_{i}_BYTE_COLUMN={column}",
            f"ERROR_{i}_REASON={reason}",
            f"ERROR_{i}_BYTES_HEX={data[start:end].hex()}",
            f"ERROR_{i}_WINDOW_HEX={window.hex()}",
        ]
    )

records.append("UTF8_DECODE=PASS" if not errors else "UTF8_DECODE=FAIL")
try:
    py_compile.compile(str(source), doraise=True)
except Exception as exc:  # noqa: BLE001 - capture evidence only
    records.append("PY_COMPILE=FAIL")
    records.append(f"PY_COMPILE_ERROR={type(exc).__name__}: {exc}")
else:
    records.append("PY_COMPILE=PASS")

out.write_text("\n".join(records) + "\n", encoding="utf-8")
PY

sha256sum "$CAPTURE_DIR"/* > "$CAPTURE_DIR/SHA256SUMS"

if grep -q '^UTF8_DECODE=FAIL$' "$CAPTURE_DIR/source-integrity.txt"; then
  STOP_REASON="SOURCE_INVALID_UTF8_GITHUB_ISSUE_199"
else
  STOP_REASON="NONE"
fi

cat > "$CAPTURE_DIR/summary.env" <<EOF
RUN_ID=$RUN_ID
TARGET_BRANCH=$TARGET_BRANCH
TARGET_FILE=$TARGET_FILE
LOCAL_SHA=$LOCAL_SHA
REMOTE_SHA=$REMOTE_SHA
MAIN_SHA=$MAIN_SHA
STOP_REASON=$STOP_REASON
EOF

EVIDENCE_BRANCH="evidence/issue199-source-integrity-$RUN_ID"
if git ls-remote --exit-code --heads origin "$EVIDENCE_BRANCH" >/dev/null 2>&1; then
  echo "STOP_REASON=EVIDENCE_BRANCH_ALREADY_EXISTS"
  exit 14
fi

git worktree add -b "$EVIDENCE_BRANCH" "$EVIDENCE_WT" "$LOCAL_SHA"
DEST="$EVIDENCE_WT/evidence/maintainer-runs/$RUN_ID"
mkdir -p "$DEST"
cp -a "$CAPTURE_DIR/." "$DEST/"

git -C "$EVIDENCE_WT" add "evidence/maintainer-runs/$RUN_ID"
git -C "$EVIDENCE_WT" diff --cached --check
git -C "$EVIDENCE_WT" -c user.name="loto-maintainer-evidence" -c user.email="noreply@localhost" commit \
  -m "chore: capture source-integrity evidence for issue #199"
git -C "$EVIDENCE_WT" push -u origin "$EVIDENCE_BRANCH"
EVIDENCE_SHA="$(git -C "$EVIDENCE_WT" rev-parse HEAD)"

COMMENT="Remote source-integrity capture completed.\n\n- run: \`$RUN_ID\`\n- source branch/head: \`$TARGET_BRANCH\` / \`$LOCAL_SHA\`\n- evidence branch: \`$EVIDENCE_BRANCH\`\n- evidence commit: \`$EVIDENCE_SHA\`\n- result: \`$STOP_REASON\`\n\nEvidence path: \`evidence/maintainer-runs/$RUN_ID/\`"
if gh issue comment "$ISSUE" --repo "$REPO" --body "$COMMENT" >/dev/null; then
  ISSUE_COMMENT=PASS
else
  ISSUE_COMMENT=FAILED_NON_FATAL
fi

cat "$CAPTURE_DIR/summary.env"
echo "EVIDENCE_BRANCH=$EVIDENCE_BRANCH"
echo "EVIDENCE_SHA=$EVIDENCE_SHA"
echo "ISSUE_COMMENT=$ISSUE_COMMENT"
echo "NEXT_ACTION=GITHUB_OR_LINEAR_REVIEW_EVIDENCE_AND_BUILD_ISOLATED_SOURCE_REPAIR_PR"
