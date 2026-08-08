#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

BRANCH="bench/platform-comparison-20260808-v1"
TARGET_SHA="f13ebf6dd4b5495eb0bd47f27375c7e47c17ce60"
REPO="arumajirou/loto_forecast_platform"
REPO_ROOT="$(git rev-parse --show-toplevel)"

invoke() {
  "$@"
}

echo "=== WSL benchmark: pull -> run -> verify -> push ==="

if ! grep -Eqi 'microsoft|wsl' /proc/sys/kernel/osrelease /proc/version 2>/dev/null; then
  echo "STOP_REASON=NOT_WSL" >&2
  exit 10
fi

invoke git -C "$REPO_ROOT" fetch origin "$BRANCH"
invoke git -C "$REPO_ROOT" switch "$BRANCH"
invoke git -C "$REPO_ROOT" pull --ff-only origin "$BRANCH"

INITIAL_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
REMOTE_HEAD="$(git -C "$REPO_ROOT" ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
[[ "$INITIAL_HEAD" == "$REMOTE_HEAD" ]]

SCRIPT="$REPO_ROOT/scripts/benchmarks/platform_wsl.sh"
[[ -s "$SCRIPT" ]]

RESULT_ROOT="$REPO_ROOT/benchmark-results"
mkdir -p "$RESULT_ROOT"
mapfile -t BEFORE < <(find "$RESULT_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'platform-bench-wsl-*' -printf '%f\n' | sort)

echo "GITHUB_TO_WSL_PULL=PASS"
echo "HARNESS_HEAD=$INITIAL_HEAD"
echo "WSL_REPO_FILESYSTEM=$(df -T "$REPO_ROOT" | awk 'NR==2 {print $2}')"

set +e
bash "$SCRIPT" "$TARGET_SHA"
RC=$?
set -e
if [[ "$RC" -ne 0 ]]; then
  echo "WSL_BENCHMARK_EXECUTION=FAIL"
  echo "STOP_REASON=BENCHMARK_EXIT_${RC}"
  exit "$RC"
fi

mapfile -t AFTER < <(find "$RESULT_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'platform-bench-wsl-*' -printf '%f\n' | sort)
NEW_DIRS=()
for d in "${AFTER[@]}"; do
  found=false
  for b in "${BEFORE[@]}"; do
    if [[ "$d" == "$b" ]]; then found=true; break; fi
  done
  if [[ "$found" == false ]]; then NEW_DIRS+=("$d"); fi
done
[[ "${#NEW_DIRS[@]}" -eq 1 ]]
REL_RESULT="benchmark-results/${NEW_DIRS[0]}"
RESULT_DIR="$REPO_ROOT/$REL_RESULT"

python3 - "$RESULT_DIR" "$TARGET_SHA" <<'PY'
from pathlib import Path
import json, sys
root = Path(sys.argv[1]); target = sys.argv[2]
for name in ("status.json", "summary.json", "metrics.csv", "platform.json", "wsl-tree.txt"):
    if not (root / name).is_file():
        raise SystemExit(f"missing {name}")
status = json.loads((root / "status.json").read_text())
summary = json.loads((root / "summary.json").read_text())
platform = json.loads((root / "platform.json").read_text())
assert status["overall_status"] == "PASS", status
assert status["valid_for_performance_comparison"] is True, status
assert status["target_sha"] == target, status
assert summary["all_stages_pass"] is True, summary
assert summary["target_sha"] == target, summary
assert summary["triton_selected"] is True, summary
assert platform["platform"] == "WSL", platform
assert platform["target_sha"] == target, platform
print("RESULT_VALIDATION=PASS")
PY

mapfile -t CHANGES < <(git -C "$REPO_ROOT" status --porcelain=v1)
BAD=()
for line in "${CHANGES[@]}"; do
  [[ -z "$line" ]] && continue
  path="${line:3}"
  case "$path" in
    "$REL_RESULT"|"$REL_RESULT"/*) ;;
    *) BAD+=("$line") ;;
  esac
done
if [[ "${#BAD[@]}" -gt 0 ]]; then
  printf 'UNEXPECTED_CHANGE=%s\n' "${BAD[*]}" >&2
  exit 30
fi

REMOTE_BEFORE="$(git -C "$REPO_ROOT" ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
[[ "$REMOTE_BEFORE" == "$INITIAL_HEAD" ]]

git -C "$REPO_ROOT" add -- "$REL_RESULT"
mapfile -t STAGED < <(git -C "$REPO_ROOT" diff --cached --name-only)
[[ "${#STAGED[@]}" -gt 0 ]]
for path in "${STAGED[@]}"; do
  [[ "$path" == "$REL_RESULT"/* ]]
done

git -C "$REPO_ROOT" commit -m "chore(bench): record successful WSL benchmark"
RESULT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
git -C "$REPO_ROOT" push origin "$BRANCH"
REMOTE_AFTER="$(git -C "$REPO_ROOT" ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
[[ "$REMOTE_AFTER" == "$RESULT_COMMIT" ]]

PR_JSON="$(gh pr view 192 --repo "$REPO" --json isDraft,headRefOid,url)"
PR_DRAFT="$(python3 -c 'import json,sys; print(str(json.load(sys.stdin)["isDraft"]).lower())' <<<"$PR_JSON")"
PR_HEAD="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["headRefOid"])' <<<"$PR_JSON")"
[[ "$PR_DRAFT" == "true" ]]
[[ "$PR_HEAD" == "$RESULT_COMMIT" ]]

echo "WSL_BENCHMARK_EXECUTION=PASS"
echo "RESULT_STATUS=PASS"
echo "WSL_RESULT_PUSH=PASS"
echo "REMOTE_HEAD_VERIFY=PASS"
echo "PR_192_REMOTE_UPDATE=PASS"
echo "RESULT_COMMIT=$RESULT_COMMIT"
echo "RESULT_DIR=$REL_RESULT"
echo "NEXT_TARGET=PLATFORM_COMPARISON_AUDIT"
echo "STOP_REASON=NONE"
