#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

TARGET_SHA="${1:-f13ebf6dd4b5495eb0bd47f27375c7e47c17ce60}"
TARGET_PR=183
REPO="arumajirou/loto_forecast_platform"
TARGET_BRANCH="fix/windows-portability-verification-v1"
EXPECTED_BASE="f5f5c5e1feb97042fe9a3c947a9a97aac2281dac"
EXPECTED_MAIN="5926ad6d00314c7ba5ec7133bb377dd5beb1316c"
UV_VERSION="0.11.21"
PYTHON_VERSION="3.12.13"

REPO_ROOT="$(git rev-parse --show-toplevel)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="platform-bench-wsl-${STAMP}"
REL_OUT="benchmark-results/${RUN_ID}"
OUT="${REPO_ROOT}/${REL_OUT}"
TARGET="${TMPDIR:-/tmp}/loto-wsl-target-$$"
UV_ROOT="${TMPDIR:-/tmp}/loto-wsl-uv-${UV_VERSION}-$$"
PHASE="startup"
UV_EXE=""
mkdir -p "$OUT"

write_status() {
  local overall="$1" phase="$2" valid="$3" error="${4:-}"
  STATUS_OVERALL="$overall" STATUS_PHASE="$phase" STATUS_VALID="$valid" STATUS_ERROR="$error" \
  RUN_ID="$RUN_ID" TARGET_SHA="$TARGET_SHA" python3 - "$OUT/status.json" <<'PY'
import json, os, sys
payload = {
    "run_id": os.environ["RUN_ID"],
    "overall_status": os.environ["STATUS_OVERALL"],
    "phase": os.environ["STATUS_PHASE"],
    "valid_for_performance_comparison": os.environ["STATUS_VALID"].lower() == "true",
    "target_sha": os.environ["TARGET_SHA"],
}
if os.environ.get("STATUS_ERROR"):
    payload["error"] = os.environ["STATUS_ERROR"]
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY
}

cleanup() {
  set +e
  if [[ -d "$TARGET" ]]; then
    git -C "$REPO_ROOT" worktree remove --force "$TARGET" >/dev/null 2>&1 || true
  fi
  rm -rf "$UV_ROOT" >/dev/null 2>&1 || true
}
trap cleanup EXIT

run_stage() {
  local name="$1" command="$2"
  echo "BENCH_STAGE=$name"
  set +e
  env REPO_ROOT="$REPO_ROOT" TARGET="$TARGET" OUT="$OUT" UV_ROOT="$UV_ROOT" UV_VERSION="$UV_VERSION" PYTHON_VERSION="$PYTHON_VERSION" UV_EXE="$UV_EXE" \
    /usr/bin/time -v -o "$OUT/${name}.time.txt" bash -lc "$command" \
    > >(tee "$OUT/${name}.log") 2> >(tee -a "$OUT/${name}.log" >&2)
  local rc=$?
  set -e
  printf 'STAGE_RC=%s\n' "$rc" > "$OUT/${name}.rc"
  if [[ "$rc" -ne 0 ]]; then
    return "$rc"
  fi
}

fail() {
  local rc=$? message="${1:-benchmark failed}"
  set +e
  write_status "FAILED" "$PHASE" "false" "$message"
  echo "WSL_LOCAL_BENCHMARK=FAIL"
  echo "FAILED_PHASE=$PHASE"
  echo "ERROR=$message"
  echo "OUTPUT=$REL_OUT"
  exit "$rc"
}
trap 'fail "command failed at phase ${PHASE}"' ERR

for cmd in git gh curl tar python3 uname lscpu df; do
  command -v "$cmd" >/dev/null || { PHASE="capability"; false; }
done
[[ -x /usr/bin/time ]] || { PHASE="capability"; false; }

if ! grep -Eqi 'microsoft|wsl' /proc/sys/kernel/osrelease /proc/version 2>/dev/null; then
  PHASE="platform_identity"
  echo "Expected WSL but Microsoft/WSL kernel marker was not found." >&2
  false
fi

PHASE="remote_guard"
PR_JSON="$(gh api "repos/$REPO/pulls/$TARGET_PR")"
MAIN_SHA="$(gh api "repos/$REPO/git/ref/heads/main" --jq '.object.sha')"
PR_HEAD="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["head"]["sha"])' <<<"$PR_JSON")"
PR_BASE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["base"]["sha"])' <<<"$PR_JSON")"
PR_DRAFT="$(python3 -c 'import json,sys; print(str(json.load(sys.stdin)["draft"]).lower())' <<<"$PR_JSON")"
[[ "$PR_HEAD" == "$TARGET_SHA" ]]
[[ "$PR_BASE" == "$EXPECTED_BASE" ]]
[[ "$MAIN_SHA" == "$EXPECTED_MAIN" ]]
[[ "$PR_DRAFT" == "true" ]]

SYSTEM_UV="NOT_INSTALLED"
if command -v uv >/dev/null 2>&1; then
  SYSTEM_UV="$(uv --version 2>/dev/null || true)"
fi

PHASE="uv_bootstrap"
mkdir -p "$UV_ROOT"
run_stage "uv_bootstrap_exact" 'set -Eeuo pipefail; uri="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz"; curl -fL --retry 3 --retry-delay 1 "$uri" -o "$UV_ROOT/uv.tar.gz"; mkdir -p "$UV_ROOT/bin"; tar -xzf "$UV_ROOT/uv.tar.gz" -C "$UV_ROOT/bin"'
UV_EXE="$(find "$UV_ROOT/bin" -type f -name uv -perm -u+x | head -n1)"
[[ -n "$UV_EXE" && -x "$UV_EXE" ]]
BENCHMARK_UV="$($UV_EXE --version)"
read -r UV_NAME UV_SEMVER _ <<<"$BENCHMARK_UV"
[[ "$UV_NAME" == "uv" && "$UV_SEMVER" == "$UV_VERSION" ]]

PHASE="platform"
OS_RELEASE="$(. /etc/os-release; printf '%s %s' "${PRETTY_NAME:-Linux}" "${VERSION_ID:-}")"
CPU_MODEL="$(lscpu | awk -F: '/Model name:/ {sub(/^[ \t]+/, "", $2); print $2; exit}')"
MEM_TOTAL_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
FS_TYPE="$(df -T "$REPO_ROOT" | awk 'NR==2 {print $2}')"
GPU_NAME="NOT_AVAILABLE"
GPU_DRIVER=""
GPU_MEMORY_MB=""
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_LINE="$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
  if [[ -n "$GPU_LINE" ]]; then
    IFS=',' read -r GPU_NAME GPU_DRIVER GPU_MEMORY_MB <<<"$GPU_LINE"
    GPU_NAME="${GPU_NAME# }"; GPU_NAME="${GPU_NAME% }"
    GPU_DRIVER="${GPU_DRIVER# }"; GPU_DRIVER="${GPU_DRIVER% }"
    GPU_MEMORY_MB="${GPU_MEMORY_MB# }"; GPU_MEMORY_MB="${GPU_MEMORY_MB% }"
  fi
fi
RUN_ID="$RUN_ID" TARGET_SHA="$TARGET_SHA" EXPECTED_BASE="$EXPECTED_BASE" EXPECTED_MAIN="$EXPECTED_MAIN" \
OS_RELEASE="$OS_RELEASE" CPU_MODEL="$CPU_MODEL" MEM_TOTAL_KB="$MEM_TOTAL_KB" FS_TYPE="$FS_TYPE" \
GPU_NAME="$GPU_NAME" GPU_DRIVER="$GPU_DRIVER" GPU_MEMORY_MB="$GPU_MEMORY_MB" \
SYSTEM_UV="$SYSTEM_UV" BENCHMARK_UV="$BENCHMARK_UV" PYTHON_VERSION="$PYTHON_VERSION" python3 - "$OUT/platform.json" <<'PY'
import json, os, platform, sys
payload = {
    "run_id": os.environ["RUN_ID"],
    "platform": "WSL",
    "os": os.environ["OS_RELEASE"],
    "kernel": platform.release(),
    "architecture": platform.machine(),
    "cpu": os.environ["CPU_MODEL"],
    "logical_processors": os.cpu_count(),
    "total_memory_gb": round(int(os.environ["MEM_TOTAL_KB"]) / 1024 / 1024, 2),
    "filesystem": os.environ["FS_TYPE"],
    "repo_path": os.getcwd(),
    "gpu": os.environ["GPU_NAME"],
    "gpu_driver": os.environ["GPU_DRIVER"],
    "gpu_memory_mb": os.environ["GPU_MEMORY_MB"],
    "system_uv": os.environ["SYSTEM_UV"],
    "benchmark_uv": os.environ["BENCHMARK_UV"],
    "benchmark_python": os.environ["PYTHON_VERSION"],
    "target_pr": 183,
    "target_sha": os.environ["TARGET_SHA"],
    "base_sha": os.environ["EXPECTED_BASE"],
    "main_sha": os.environ["EXPECTED_MAIN"],
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY

echo "SYSTEM_UV=$SYSTEM_UV"
echo "BENCHMARK_UV=$BENCHMARK_UV"
echo "BENCHMARK_PYTHON=$PYTHON_VERSION"
echo "WSL_FILESYSTEM=$FS_TYPE"

PHASE="target_fetch"
git -C "$REPO_ROOT" fetch --no-tags origin "+refs/heads/$TARGET_BRANCH:refs/remotes/origin/$TARGET_BRANCH"
FETCHED_TARGET="$(git -C "$REPO_ROOT" rev-parse "refs/remotes/origin/$TARGET_BRANCH")"
[[ "$FETCHED_TARGET" == "$TARGET_SHA" ]]
rm -rf "$TARGET"
git -C "$REPO_ROOT" worktree add --detach "$TARGET" "$TARGET_SHA"
[[ "$(git -C "$TARGET" rev-parse HEAD)" == "$TARGET_SHA" ]]

PHASE="python"
run_stage "uv_python_312_ready" '"$UV_EXE" python install "$PYTHON_VERSION"'
PY_EXE="$($UV_EXE python find "$PYTHON_VERSION")"
[[ -x "$PY_EXE" ]]
[[ "$($PY_EXE --version)" == "Python $PYTHON_VERSION" ]]

PHASE="lock"
run_stage "uv_lock_check" 'cd "$TARGET"; "$UV_EXE" lock --check'

PHASE="resolve"
run_stage "wsl_resolve_first" 'cd "$TARGET"; "$UV_EXE" sync --dry-run --locked --python "$PYTHON_VERSION"'
run_stage "wsl_resolve_second" 'cd "$TARGET"; "$UV_EXE" sync --dry-run --locked --python "$PYTHON_VERSION"'

PHASE="dependency_tree"
run_stage "wsl_dependency_tree" 'cd "$TARGET"; "$UV_EXE" tree --locked --python-version 3.12 --python-platform x86_64-unknown-linux-gnu | tee "$OUT/wsl-tree.txt"'
if ! grep -Eqi '(^|[^[:alnum:]_-])triton([[:space:]]|$)' "$OUT/wsl-tree.txt"; then
  echo "Expected Linux/WSL dependency tree to select Triton, but it did not." >&2
  false
fi

PHASE="compile"
run_stage "python_compile_src" 'cd "$TARGET"; '"$(printf '%q' "$PY_EXE")"' -m compileall -q src'

PHASE="wheel"
DIST="$TARGET/.benchmark-dist"
mkdir -p "$DIST"
run_stage "wheel_build" 'cd "$TARGET"; "$UV_EXE" build --wheel --out-dir "$TARGET/.benchmark-dist"'
WHEEL="$(find "$DIST" -maxdepth 1 -type f -name '*.whl' | head -n1)"
[[ -n "$WHEEL" ]]

PHASE="wheel_import"
VENV="$TARGET/.venv-portability-bench"
run_stage "wheel_install_import_312" 'cd "$TARGET"; "$UV_EXE" venv "$TARGET/.venv-portability-bench" --python "$PYTHON_VERSION"; "$UV_EXE" pip install --python "$TARGET/.venv-portability-bench/bin/python" --no-deps '"$(printf '%q' "$WHEEL")"'; "$TARGET/.venv-portability-bench/bin/python" -c "import loto; print(\"loto_version=\" + loto.__version__)"'

PHASE="results"
python3 - "$OUT" <<'PY'
from pathlib import Path
import csv, json, re, sys
root = Path(sys.argv[1])
order = [
    "uv_bootstrap_exact", "uv_python_312_ready", "uv_lock_check",
    "wsl_resolve_first", "wsl_resolve_second", "wsl_dependency_tree",
    "python_compile_src", "wheel_build", "wheel_install_import_312",
]

def wall_seconds(v: str) -> float:
    parts = v.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(v)

rows = []
for stage in order:
    text = (root / f"{stage}.time.txt").read_text(errors="replace")
    rc_text = (root / f"{stage}.rc").read_text().strip()
    if rc_text != "STAGE_RC=0":
        raise SystemExit(f"{stage} failed")
    row = {"stage": stage, "success": True}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Elapsed (wall clock) time"):
            row["wall_seconds"] = round(wall_seconds(line.rsplit(": ", 1)[1]), 3)
        elif line.startswith("Percent of CPU this job got:"):
            row["cpu_pct"] = float(line.split(":", 1)[1].strip().rstrip("%"))
        elif line.startswith("Maximum resident set size (kbytes):"):
            row["max_rss_kb"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("File system inputs:"):
            row["fs_inputs"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("File system outputs:"):
            row["fs_outputs"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("Voluntary context switches:"):
            row["vol_ctx"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("Involuntary context switches:"):
            row["invol_ctx"] = int(line.split(":", 1)[1].strip())
    if "wall_seconds" not in row:
        raise SystemExit(f"missing wall time for {stage}")
    rows.append(row)

with (root / "metrics.csv").open("w", newline="", encoding="utf-8") as fh:
    fields = ["stage", "wall_seconds", "cpu_pct", "max_rss_kb", "fs_inputs", "fs_outputs", "vol_ctx", "invol_ctx", "success"]
    writer = csv.DictWriter(fh, fieldnames=fields)
    writer.writeheader(); writer.writerows(rows)

summary = {
    "run_id": root.name,
    "platform": "WSL",
    "target_sha": "f13ebf6dd4b5495eb0bd47f27375c7e47c17ce60",
    "target_pr": 183,
    "benchmark_uv": "0.11.21",
    "benchmark_python": "3.12.13",
    "triton_selected": True,
    "all_stages_pass": True,
    "stages": rows,
}
(root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY
write_status "PASS" "complete" "true"

echo "WSL_TRITON_SELECTED=true"
echo "WSL_LOCAL_BENCHMARK=PASS"
echo "RUN_ID=$RUN_ID"
echo "OUTPUT=$REL_OUT"
echo "TARGET_SHA=$TARGET_SHA"
trap - ERR
