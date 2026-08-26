#!/usr/bin/env bash
set -Eeuo pipefail

# Publish an already VERIFIED local Phase 4C GluonTS compat P6 lifecycle run
# into ops/runtime-audit-handoff without rerunning the model campaign.
#
# Usage:
#   bash handoff/tools/phase4c_publish_verified_local.sh [LOCAL_ARTIFACT_DIR]
#
# If LOCAL_ARTIFACT_DIR is omitted, the newest
# /mnt/e/env/ts/loto_forecast_platform/artifacts/phase4c-gluonts-compat-smoke-*
# directory is selected.

ROOT="${LOTO_ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
SOURCE_WT="${LOTO_SOURCE_WT:-/mnt/e/env/ts/worktrees/loto-runtime-audit-20260826-121248}"
HANDOFF_WT="${LOTO_HANDOFF_WT:-/mnt/e/env/ts/worktrees/loto-runtime-handoff}"
HANDOFF="$HANDOFF_WT/handoff"
BRANCH="ops/runtime-audit-handoff"
EXPECTED_SOURCE_SHA="8af95b2be18280589cbbb13aa1fc32dfb793767c"
EXPECTED_ENV="environments/gluonts-compat"
EXPECTED_GLUONTS="0.16.3"
EXPECTED_TORCH_PREFIX="2.9.1"

if [[ $# -ge 1 ]]; then
  OUT="$1"
else
  OUT="$(
    find "$ROOT/artifacts" -maxdepth 1 -type d \
      -name 'phase4c-gluonts-compat-smoke-*' \
      -printf '%T@ %p\n' 2>/dev/null \
      | sort -nr \
      | head -1 \
      | cut -d' ' -f2-
  )"
fi

if [[ -z "${OUT:-}" || ! -d "$OUT" ]]; then
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=LOCAL_ARTIFACT_DIR_NOT_FOUND"
  exit 2
fi

RUN_ID="$(basename "$OUT" | sed 's/^phase4c-gluonts-compat-smoke-//')"
PUBLISH_LOG="$OUT/publish-to-handoff.log"
PUBLISH_EXIT="$OUT/publish-exitcode.txt"
TARGET="$HANDOFF/phase4c"

finish() {
  local rc=$?
  trap - EXIT
  printf '%s\n' "$rc" > "$PUBLISH_EXIT" 2>/dev/null || true
  echo
  echo "============================================================"
  echo "PHASE4C_PUBLISH_FINAL_EXIT_CODE=$rc"
  echo "LOCAL_ARTIFACT_DIR=$OUT"
  echo "PUBLISH_LOG=$PUBLISH_LOG"
  echo "============================================================"
  if [[ -t 0 ]]; then
    read -r -p "Enterキーで終了します..." _ || true
  fi
  exit "$rc"
}
trap finish EXIT

exec > >(tee -a "$PUBLISH_LOG") 2>&1

echo "============================================================"
echo "PHASE 4C VERIFIED LOCAL EVIDENCE -> GITHUB HANDOFF"
echo "============================================================"
echo "RUN_ID=$RUN_ID"
echo "OUT=$OUT"
echo "HANDOFF_WT=$HANDOFF_WT"
echo "BRANCH=$BRANCH"

echo
echo "=== 1. REQUIRED LOCAL EVIDENCE ==="
for f in summary.json runtime-probe.json provider-registry.json SHA256SUMS; do
  if [[ ! -f "$OUT/$f" ]]; then
    echo "PHASE4C_PUBLISH=BLOCKED"
    echo "REASON=MISSING_LOCAL_EVIDENCE:$f"
    exit 10
  fi
  echo "FOUND=$OUT/$f"
done

if [[ -f "$OUT/exitcode.txt" ]]; then
  LOCAL_RC="$(tr -d '[:space:]' < "$OUT/exitcode.txt")"
  echo "LOCAL_EXIT_CODE=$LOCAL_RC"
  [[ "$LOCAL_RC" == "0" ]] || {
    echo "PHASE4C_PUBLISH=BLOCKED"
    echo "REASON=LOCAL_RUN_NONZERO"
    exit 11
  }
fi

echo
echo "=== 2. LOCAL SHA-256 VERIFY ==="
(
  cd /
  sha256sum -c "$OUT/SHA256SUMS"
)
echo "LOCAL_SHA256_GATE=PASS"

echo
echo "=== 3. SEMANTIC EVIDENCE GATE ==="
python3 - "$OUT/summary.json" "$OUT/runtime-probe.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text("utf-8"))
runtime = json.loads(Path(sys.argv[2]).read_text("utf-8").splitlines()[-1])

expected_models = (
    "DeepNPTSEstimator",
    "DeepAREstimator",
    "TiDEEstimator",
    "SimpleFeedForwardEstimator",
    "TemporalFusionTransformerEstimator",
    "WaveNetEstimator",
    "DLinearEstimator",
    "PatchTSTEstimator",
    "LagTSTEstimator",
)

assert summary.get("phase") == "PHASE4C_GLUONTS_COMPAT_P6_LIFECYCLE", summary.get("phase")
assert summary.get("status") == "VERIFIED", summary.get("status")
assert summary.get("environment") == "environments/gluonts-compat", summary.get("environment")
assert summary.get("expected_gluonts") == "0.16.3", summary.get("expected_gluonts")
assert str(summary.get("expected_torch_family", "")).startswith("2.9.1"), summary.get("expected_torch_family")
assert summary.get("device_policy", {}).get("requested_by_repository_p6") == "cpu"
assert summary.get("device_policy", {}).get("gpu_execution_claimed") is False
assert summary.get("dataset_policy", {}).get("accuracy_ranking") is False

checks = summary.get("validation", {}).get("checks", {})
required_checks = (
    "campaign_returncode_zero",
    "campaign_status_verified",
    "nine_models_present",
    "model_order_exact",
    "all_model_statuses_verified",
    "fit_reload_present_all",
    "fit_checks_pass_all",
    "reload_checks_pass_all",
    "device_cpu_contract_all",
    "separate_process_reload_all",
    "all_critical_checks_pass",
)
for key in required_checks:
    assert checks.get(key) is True, (key, checks.get(key))

models = summary.get("validation", {}).get("models", [])
assert len(models) == 9, len(models)
assert tuple(row.get("model_class") for row in models) == expected_models
for row in models:
    assert row.get("status") == "VERIFIED", row
    assert not row.get("errors"), row
    fit_pid = row.get("fit_process_id")
    reload_pid = row.get("reload_process_id")
    assert fit_pid and reload_pid and int(fit_pid) != int(reload_pid), row
    assert row.get("fit_checks", {}).get("device") == "PASS", row
    assert row.get("reload_checks", {}).get("device") == "PASS", row
    assert all(v == "PASS" for v in row.get("fit_checks", {}).values()), row
    assert all(v == "PASS" for v in row.get("reload_checks", {}).values()), row

assert runtime.get("gluonts") == "0.16.3", runtime
assert str(runtime.get("torch", "")).startswith("2.9.1"), runtime
assert runtime.get("prefix", "").endswith("/environments/gluonts-compat/.venv"), runtime

print("SEMANTIC_EVIDENCE_GATE=PASS")
print(f"RUNTIME_PYTHON={runtime.get('python')}")
print(f"RUNTIME_GLUONTS={runtime.get('gluonts')}")
print(f"RUNTIME_TORCH={runtime.get('torch')}")
print(f"CUDA_VISIBLE_OUTSIDE_PROVIDER={runtime.get('torch_cuda_available_outside_provider')}")
print("GPU_EXECUTION_CLAIMED=FALSE")
PY

echo
echo "=== 4. SOURCE WORKTREE GATE ==="
SOURCE_HEAD="$(git -C "$SOURCE_WT" rev-parse HEAD)"
echo "EXPECTED_SOURCE_SHA=$EXPECTED_SOURCE_SHA"
echo "ACTUAL_SOURCE_SHA=$SOURCE_HEAD"
[[ "$SOURCE_HEAD" == "$EXPECTED_SOURCE_SHA" ]] || {
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=SOURCE_SHA_MISMATCH"
  exit 20
}
[[ -z "$(git -C "$SOURCE_WT" status --porcelain)" ]] || {
  git -C "$SOURCE_WT" status --short
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=SOURCE_WORKTREE_DIRTY"
  exit 21
}
echo "SOURCE_GATE=PASS"

echo
echo "=== 5. HANDOFF SYNC GATE ==="
[[ "$(git -C "$HANDOFF_WT" branch --show-current)" == "$BRANCH" ]] || {
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=WRONG_HANDOFF_BRANCH"
  exit 22
}
[[ -z "$(git -C "$HANDOFF_WT" status --porcelain)" ]] || {
  git -C "$HANDOFF_WT" status --short
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=HANDOFF_WORKTREE_DIRTY"
  exit 23
}

git -C "$HANDOFF_WT" fetch --prune origin
git -C "$HANDOFF_WT" pull --ff-only origin "$BRANCH"

LOCAL_HEAD="$(git -C "$HANDOFF_WT" rev-parse HEAD)"
REMOTE_HEAD="$(git -C "$HANDOFF_WT" rev-parse "origin/$BRANCH")"
echo "HANDOFF_LOCAL_HEAD=$LOCAL_HEAD"
echo "HANDOFF_REMOTE_HEAD=$REMOTE_HEAD"
[[ "$LOCAL_HEAD" == "$REMOTE_HEAD" ]] || {
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=HANDOFF_REMOTE_MISMATCH_AFTER_PULL"
  exit 24
}
echo "HANDOFF_SYNC_GATE=PASS"

echo
echo "=== 6. COPY REVIEWABLE EVIDENCE ONLY ==="
rm -rf "$TARGET"
mkdir -p "$TARGET"

while IFS= read -r -d '' src; do
  rel="${src#"$OUT"/}"
  case "/$rel/" in
    */predictors/*) continue ;;
  esac
  case "$src" in
    *.json|*.jsonl|*.md|*.log|*.txt|*.tsv)
      mkdir -p "$TARGET/$(dirname "$rel")"
      cp -p "$src" "$TARGET/$rel"
      ;;
  esac
done < <(find "$OUT" -type f -print0 | sort -z)

cp -p "$OUT/SHA256SUMS" "$TARGET/LOCAL_SHA256SUMS"

echo "PUBLISHED_EVIDENCE_FILES=$(find "$TARGET" -type f | wc -l)"

if find "$TARGET" -type f -size +94M -print -quit | grep -q .; then
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=PUBLISHED_FILE_TOO_LARGE"
  exit 30
fi

echo
echo "=== 7. WRITE REPORT + UPDATE CANONICAL HANDOFF ==="
python3 - "$HANDOFF" "$TARGET" "$RUN_ID" "$EXPECTED_SOURCE_SHA" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

handoff_dir = Path(sys.argv[1])
target = Path(sys.argv[2])
run_id = sys.argv[3]
source_sha = sys.argv[4]

summary = json.loads((target / "summary.json").read_text("utf-8"))
runtime = json.loads((target / "runtime-probe.json").read_text("utf-8").splitlines()[-1])

report = target / "PHASE4C_REPORT.md"
checks = summary["validation"]["checks"]
models = summary["validation"]["models"]
report.write_text(
    "\n".join(
        [
            "# Phase 4C — GluonTS compat P6 lifecycle smoke",
            "",
            f"- status: **{summary['status']}**",
            f"- local run id: `{run_id}`",
            f"- source SHA: `{source_sha}`",
            f"- environment: `{summary['environment']}`",
            f"- runtime Python: `{runtime.get('python')}`",
            f"- GluonTS: `{runtime.get('gluonts')}`",
            f"- Torch: `{runtime.get('torch')}`",
            f"- Torch CUDA build visible outside provider: `{runtime.get('torch_cuda_build')}`",
            "- formal P6 device policy: **CPU pinned**",
            "- GPU model execution: **NOT CLAIMED**",
            "- model count: **9**",
            "- lifecycle: FIT_SERIALIZE → separate-process LOAD_PREDICT",
            "- dataset: deterministic certification fixture; **not an accuracy-ranking dataset**",
            "- Phase 6 remains responsible for Hit@±1 / MAE / MSE / RMSE ranking",
            "",
            "## Critical checks",
            "",
            *[f"- {k}: `{v}`" for k, v in checks.items()],
            "",
            "## Models",
            "",
            *[
                f"- `{row['model_class']}`: `{row['status']}` "
                f"(fit pid={row['fit_process_id']}, reload pid={row['reload_process_id']})"
                for row in models
            ],
            "",
            "## Interpretation",
            "",
            "Phase 4C certifies the existing GluonTS 0.16.3 compatibility lane against the repository P6 CPU lifecycle contract. CUDA availability in the outer runtime is provenance only and is not evidence of model GPU execution.",
        ]
    )
    + "\n",
    encoding="utf-8",
)

handoff_path = handoff_dir / "HANDOFF.json"
handoff = json.loads(handoff_path.read_text("utf-8"))
handoff["handoff_run_id"] = run_id
handoff["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
handoff.setdefault("completed_phases", {})["phase4c"] = "VERIFIED"
handoff["current_phase"] = "phase4c_gluonts_compat_verified_phase4_remaining_next"
handoff["phase4c"] = {
    **summary,
    "runtime": runtime,
    "published_from_existing_local_verified_run": True,
}
handoff_path.write_text(
    json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

progress = handoff.get("estimated_progress_percent", "unknown")
current = handoff_dir / "CURRENT_STATUS.md"
progress_line = (
    f"- estimated progress: `{progress}%`"
    if isinstance(progress, (int, float))
    else f"- estimated progress: `{progress}`"
)
current.write_text(
    "\n".join(
        [
            "# Loto Forecast Runtime Audit Handoff",
            "",
            f"Updated: {datetime.now().astimezone().isoformat()}",
            "",
            "## Current overall status",
            "",
            progress_line,
            "- Phase 4A Darts GPU smoke: `VERIFIED`",
            "- Phase 4B GluonTS latest P6 lifecycle: `VERIFIED`",
            "- Phase 4C GluonTS compat P6 lifecycle: `VERIFIED`",
            f"- source SHA: `{source_sha}`",
            "",
            "## Phase 4C",
            "",
            f"- local run id: `{run_id}`",
            f"- runtime: `{runtime.get('executable')}`",
            f"- GluonTS: `{runtime.get('gluonts')}`",
            f"- Torch: `{runtime.get('torch')}`",
            "- P6 models: `9`",
            "- lifecycle: `FIT_SERIALIZE -> separate-process LOAD_PREDICT`",
            "- execution policy: `CPU pinned by repository P6 contract`",
            "- GPU execution claimed: `False`",
            "- all critical checks: `True`",
            "- fixture: `deterministic certification series; non-ranking`",
            "",
            "## Next",
            "",
            "Continue the remaining Phase 4 ready queue from `handoff/phase3d/phase4-ready-queue.tsv`. Keep runtime certification separate from Phase 6 accuracy ranking, and do not infer GPU model execution from CUDA visibility alone.",
        ]
    )
    + "\n",
    encoding="utf-8",
)

print("CANONICAL_HANDOFF_UPDATE=PASS")
PY

echo
echo "=== 8. REGENERATE MANIFESTS ==="
FILE_SIZES="$HANDOFF/FILE_SIZES.tsv"
find "$HANDOFF" -type f -printf '%s\t%p\n' \
  | sort -nr \
  > "$FILE_SIZES.tmp"
mv "$FILE_SIZES.tmp" "$FILE_SIZES"

if awk -F '\t' '$1 >= 95000000 { print; bad=1 } END { exit bad ? 0 : 1 }' "$FILE_SIZES" | grep -q .; then
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=HANDOFF_FILE_SIZE_GATE_FAILED"
  exit 31
fi

SUMS="$HANDOFF/SHA256SUMS"
(
  cd "$HANDOFF_WT"
  find handoff -type f ! -path 'handoff/SHA256SUMS' -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    > "$SUMS"
)

echo "MANIFEST_GATE=PASS"

echo
echo "=== 9. GIT REVIEW GATE ==="
git -C "$HANDOFF_WT" add handoff

git -C "$HANDOFF_WT" diff --cached --check

echo "--- staged status ---"
git -C "$HANDOFF_WT" status --short

echo "--- staged stat ---"
git -C "$HANDOFF_WT" diff --cached --stat

# Fail closed on common secret material in staged textual diff.
if git -C "$HANDOFF_WT" diff --cached --no-ext-diff -U0 \
  | grep '^+' \
  | grep -E -i '(BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|password[[:space:]]*[:=][[:space:]]*[^*[:space:]])' \
  >/dev/null; then
  echo "PHASE4C_PUBLISH=BLOCKED"
  echo "REASON=POTENTIAL_SECRET_IN_STAGED_DIFF"
  git -C "$HANDOFF_WT" reset
  exit 40
fi

echo "GIT_REVIEW_GATE=PASS"

echo
echo "=== 10. COMMIT + PUSH ==="
if git -C "$HANDOFF_WT" diff --cached --quiet; then
  echo "NO_STAGED_DIFF=TRUE"
else
  git -C "$HANDOFF_WT" commit \
    -m "audit: publish Phase 4C GluonTS compat smoke $RUN_ID"
fi

git -C "$HANDOFF_WT" push origin "$BRANCH"
git -C "$HANDOFF_WT" fetch origin "$BRANCH"

FINAL_LOCAL="$(git -C "$HANDOFF_WT" rev-parse HEAD)"
FINAL_REMOTE="$(git -C "$HANDOFF_WT" rev-parse "origin/$BRANCH")"

echo "FINAL_LOCAL_HEAD=$FINAL_LOCAL"
echo "FINAL_REMOTE_HEAD=$FINAL_REMOTE"
[[ "$FINAL_LOCAL" == "$FINAL_REMOTE" ]] || {
  echo "PHASE4C_PUBLISH=FAILED"
  echo "REASON=REMOTE_VERIFY_FAILED"
  exit 50
}

echo
echo "============================================================"
echo "PHASE4C_GLUONTS_COMPAT_PUBLISH=VERIFIED"
echo "HANDOFF_HEAD=$FINAL_LOCAL"
echo "REPORT=$TARGET/PHASE4C_REPORT.md"
echo "SUMMARY=$TARGET/summary.json"
echo "NEXT_MESSAGE=@GitHub ops/runtime-audit-handoff のPhase 4C publish結果を確認して次へ進めてください"
echo "============================================================"
