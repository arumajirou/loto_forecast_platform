#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
TOOLS_ROOT="$REPO_ROOT/tools/phase7_holdout_runner"
REQ_FILE="$TOOLS_ROOT/linux-runtime-requirements.txt"

EXPECTED_RUNNER_SHA="986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
EXPECTED_DERIVED_SHA="8077ccf023f9100344206f588dadae655eb828f3529c4d4d83ebf89c9c1ee074"
EXPECTED_FREEZE_SHA="deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c"
EXPECTED_DEV_SHA="f6e0292347cd03acea95b5c788eaa51436a8b9e7e42d2fc000e9b9d366e2557e"
EXPECTED_CANONICAL_SHA="88fd7bf24d2864fce74e95bf6475ff4b0292446f1354d403105970d095d6592f"
SCIENTIFIC_GIT_COMMIT="179bcbc9a51a60f0badfe7faa25f3818ab686229"
EXPECTED_DRAWS=50

EVIDENCE_ROOT="${PHASE7_EVIDENCE_ROOT:-/mnt/e/env/ts/phase7_evidence}"
RUNTIME_ROOT="${PHASE7_RUNTIME_ROOT:-$HOME/.cache/loto-phase7-linux-v1}"
PYTHON_VERSION="${PHASE7_PYTHON_VERSION:-3.13}"
COMPAT_HOME="$RUNTIME_ROOT/compat-home"
COMPAT_DOWNLOADS="$COMPAT_HOME/Downloads"
REPLAY_CERT="$RUNTIME_ROOT/LINUX_REPLAY_CERT.json"

PHASE7_DIR="$EVIDENCE_ROOT/automlforecast-phase7-holdout-20260818-101611"
PHASE6C_DIR="$EVIDENCE_ROOT/automlforecast-phase6c-ensemble-freeze-20260818-101021"
PHASE3_DIR="$EVIDENCE_ROOT/automlforecast-phase3-input-size-20260817-173808"
RUNNER="$PHASE7_DIR/phase7_holdout.py"
ORIGINAL_PROGRESS="$PHASE7_DIR/artifacts/progress.json"
FREEZE="$PHASE6C_DIR/artifacts/CANDIDATE_FREEZE.json"
FROZEN_EVIDENCE="$PHASE6C_DIR/artifacts/frozen_component_evidence"
DEVELOPMENT="$PHASE3_DIR/artifacts/numbers3-development-only.csv"
SOURCE_POINTER="$EVIDENCE_ROOT/numbers3-current-canonical-path.txt"

MODE="${1:-status}"

fail() {
    echo "STATUS=BLOCKED"
    echo "REASON=$*"
    echo "HOLDOUT_EXECUTED=NO"
    exit 20
}

stage() {
    local current="$1" total="$2" text="$3"
    local pct=$(( current * 100 / total ))
    printf '[%d/%d] %3d%% %s\n' "$current" "$total" "$pct" "$text"
}

sha256_file() {
    sha256sum "$1" | awk '{print $1}'
}

require_sha() {
    local path="$1" expected="$2" label="$3"
    [[ -f "$path" ]] || fail "$label missing: $path"
    local actual
    actual="$(sha256_file "$path")"
    [[ "$actual" == "$expected" ]] || fail "$label SHA mismatch expected=$expected actual=$actual path=$path"
    echo "$label=PASS sha256=$actual"
}

resolve_canonical() {
    if [[ -n "${PHASE7_CANONICAL_PATH:-}" ]]; then
        [[ -f "$PHASE7_CANONICAL_PATH" ]] || fail "PHASE7_CANONICAL_PATH missing: $PHASE7_CANONICAL_PATH"
        printf '%s\n' "$PHASE7_CANONICAL_PATH"
        return
    fi

    [[ -f "$SOURCE_POINTER" ]] || fail "canonical pointer missing; set PHASE7_CANONICAL_PATH or provide $SOURCE_POINTER"
    local candidate
    candidate="$(awk 'NF {print; exit}' "$SOURCE_POINTER")"
    [[ -n "$candidate" ]] || fail "canonical pointer is empty: $SOURCE_POINTER"
    [[ -f "$candidate" ]] || fail "canonical pointer target is not valid on Linux; set PHASE7_CANONICAL_PATH explicitly: $candidate"
    printf '%s\n' "$candidate"
}

verify_original_progress() {
    [[ -f "$ORIGINAL_PROGRESS" ]] || fail "original Phase7 progress missing: $ORIGINAL_PROGRESS"
    python3 - "$ORIGINAL_PROGRESS" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
state = payload.get("state", payload.get("phase"))
if state != "REPLAY_VERIFICATION":
    raise SystemExit(f"unexpected original state: {state!r}")
if int(payload.get("holdout_draws_done", 0)) != 0:
    raise SystemExit("original holdout_draws_done is nonzero")
if int(payload.get("actuals_accessed", 0)) != 0:
    raise SystemExit("original actuals_accessed is nonzero")
print("ORIGINAL_PHASE7_STATE=REPLAY_VERIFICATION")
print("ORIGINAL_HOLDOUT_DRAWS=0")
print("ORIGINAL_ACTUALS_ACCESSED=0")
PY
}

verify_evidence() {
    stage 1 6 "verify immutable Phase 7 evidence"
    [[ -d "$EVIDENCE_ROOT" ]] || fail "evidence root missing: $EVIDENCE_ROOT"
    [[ -d "$FROZEN_EVIDENCE" ]] || fail "frozen component evidence missing: $FROZEN_EVIDENCE"
    require_sha "$RUNNER" "$EXPECTED_RUNNER_SHA" "SEALED_ORIGINAL_RUNNER"
    require_sha "$FREEZE" "$EXPECTED_FREEZE_SHA" "CANDIDATE_FREEZE"
    require_sha "$DEVELOPMENT" "$EXPECTED_DEV_SHA" "DEVELOPMENT"
    CANONICAL_PATH="$(resolve_canonical)"
    require_sha "$CANONICAL_PATH" "$EXPECTED_CANONICAL_SHA" "CANONICAL"
    verify_original_progress
    export CANONICAL_PATH
}

link_exact() {
    local source="$1" dest="$2"
    if [[ -L "$dest" ]]; then
        [[ "$(readlink -f "$dest")" == "$(readlink -f "$source")" ]] || fail "compatibility link points elsewhere: $dest"
    elif [[ -e "$dest" ]]; then
        fail "compatibility path already exists and is not a symlink: $dest"
    else
        ln -s "$source" "$dest"
    fi
}

prepare_compat_home() {
    stage 2 6 "prepare persistent Linux compatibility home"
    mkdir -p "$COMPAT_DOWNLOADS"
    link_exact "$PHASE7_DIR" "$COMPAT_DOWNLOADS/automlforecast-phase7-holdout-20260818-101611"
    link_exact "$PHASE6C_DIR" "$COMPAT_DOWNLOADS/automlforecast-phase6c-ensemble-freeze-20260818-101021"
    link_exact "$PHASE3_DIR" "$COMPAT_DOWNLOADS/automlforecast-phase3-input-size-20260817-173808"
    printf '%s\n' "$CANONICAL_PATH" > "$COMPAT_DOWNLOADS/numbers3-current-canonical-path.txt"
    echo "COMPAT_HOME=$COMPAT_HOME"
}

ensure_runtime() {
    stage 3 6 "provision exact uv runtime"
    command -v uv >/dev/null 2>&1 || fail "uv is required"
    [[ -f "$REQ_FILE" ]] || fail "runtime requirements missing: $REQ_FILE"

    local req_sha safe_py venv python marker
    req_sha="$(sha256_file "$REQ_FILE")"
    safe_py="${PYTHON_VERSION//./_}"
    venv="$RUNTIME_ROOT/venv-${safe_py}-${req_sha:0:16}"
    python="$venv/bin/python"
    marker="$venv/.phase7-runtime-ready"

    mkdir -p "$RUNTIME_ROOT"
    if [[ ! -x "$python" || ! -f "$marker" || "$(cat "$marker" 2>/dev/null || true)" != "$req_sha" ]]; then
        rm -rf -- "$venv"
        uv venv --python "$PYTHON_VERSION" "$venv"
        uv pip install --python "$python" -r "$REQ_FILE"
        printf '%s\n' "$req_sha" > "$marker"
        uv pip freeze --python "$python" > "$venv/phase7-runtime-freeze.txt"
    fi

    "$python" - <<'PY'
from importlib.metadata import version

expected = {
    "mlforecast": "1.1.0",
    "optuna": "4.9.0",
    "catboost": "1.2.10",
    "pandas": "2.3.3",
    "numpy": "2.5.2",
    "scikit-learn": "1.9.0",
}
for package, wanted in expected.items():
    actual = version(package)
    if actual != wanted:
        raise SystemExit(f"runtime mismatch {package}: expected={wanted} actual={actual}")
    print(f"RUNTIME_{package.upper().replace('-', '_')}={actual}")
PY

    PHASE7_PYTHON="$python"
    export PHASE7_PYTHON
    echo "PHASE7_PYTHON=$PHASE7_PYTHON"
}

verify_repo() {
    stage 4 6 "verify repository scientific ancestry"
    local head
    head="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    git -C "$REPO_ROOT" merge-base --is-ancestor e3b05bec7382c4571f4b1a05df054eda5f6d99fb HEAD \
        || fail "scientific main ancestor is not present"
    echo "REPO_HEAD=$head"
}

progress_bar() {
    local done="$1" total="$2" label="$3"
    local width=40 filled empty pct
    (( done < 0 )) && done=0
    (( done > total )) && done=$total
    pct=$(( done * 100 / total ))
    filled=$(( done * width / total ))
    empty=$(( width - filled ))
    printf '\r['
    printf '%*s' "$filled" '' | tr ' ' '#'
    printf '%*s' "$empty" '' | tr ' ' '-'
    printf '] %3d%% %s' "$pct" "$label"
}

write_sha256sums() {
    local root="$1"
    (
        cd "$root"
        find . -type f ! -name SHA256SUMS -print0 \
            | sort -z \
            | xargs -0 -r sha256sum \
            > SHA256SUMS
    )
}

run_preflight() {
    local stamp out
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    out="$COMPAT_DOWNLOADS/phase7-linux-preflight-v1-$stamp"
    stage 5 6 "run merged-main preflight"
    HOME="$COMPAT_HOME" "$PHASE7_PYTHON" "$TOOLS_ROOT/main_preflight.py" \
        --repo-root "$REPO_ROOT" \
        --output-root "$out"
    stage 6 6 "preflight complete"
    echo "LINUX_PREFLIGHT_ROOT=$out"
}

verify_replay_artifacts() {
    local artifacts="$1" root="$2" head
    head="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    "$PHASE7_PYTHON" - "$artifacts" "$REPLAY_CERT" "$head" "$EXPECTED_FREEZE_SHA" "$EXPECTED_DEV_SHA" "$EXPECTED_CANONICAL_SHA" <<'PY'
import json
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

artifacts = Path(sys.argv[1])
cert_path = Path(sys.argv[2])
head, freeze_sha, dev_sha, canonical_sha = sys.argv[3:7]
replay = json.loads((artifacts / "REPLAY_ONLY_VERIFICATION.json").read_text(encoding="utf-8"))
progress = json.loads((artifacts / "progress.json").read_text(encoding="utf-8"))
if replay.get("status") != "PASS":
    raise SystemExit("replay status is not PASS")
if int(replay.get("components_verified", -1)) != 4:
    raise SystemExit("replay components != 4")
if int(replay.get("verification_trial_count", -1)) != 80:
    raise SystemExit("replay trials != 80")
if int(replay.get("holdout_draws_accessed", -1)) != 0:
    raise SystemExit("replay holdout access is nonzero")
if int(replay.get("actuals_accessed", -1)) != 0:
    raise SystemExit("replay actual access is nonzero")
if replay.get("holdout_executed") is not False:
    raise SystemExit("replay reports holdout execution")
if int(progress.get("holdout_draws_done", -1)) != 0:
    raise SystemExit("replay progress holdout draws are nonzero")
if int(progress.get("actuals_accessed", -1)) != 0:
    raise SystemExit("replay progress actuals are nonzero")

runtime = {
    package: version(package)
    for package in ["mlforecast", "optuna", "catboost", "pandas", "numpy", "scikit-learn"]
}
payload = {
    "schema_version": "phase7-linux-replay-cert/v1",
    "status": "PASS",
    "repo_head": head,
    "candidate_freeze_sha256": freeze_sha,
    "development_sha256": dev_sha,
    "canonical_sha256": canonical_sha,
    "components_verified": 4,
    "verification_trial_count": 80,
    "holdout_draws_accessed": 0,
    "actuals_accessed": 0,
    "holdout_executed": False,
    "runtime": runtime,
    "verified_at_utc": datetime.now(UTC).isoformat(),
}
cert_path.parent.mkdir(parents=True, exist_ok=True)
cert_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("ALL_4_SEED_CANONICAL_MATCH=PASS")
print("ALL_80_TRIALS_REPLAYED=PASS")
print("HOLDOUT_DRAWS_ACCESSED=0")
print("ACTUALS_ACCESSED=0")
print(f"LINUX_REPLAY_CERT={cert_path}")
PY
    write_sha256sums "$root"
}

run_replay() {
    local stamp root preflight derived artifacts pid rc done
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    root="$COMPAT_DOWNLOADS/phase7-linux-replay-v1-$stamp"
    preflight="$root/preflight"
    artifacts="$root/artifacts"
    mkdir -p "$root"

    echo "REPLAY_STAGE=preflight"
    HOME="$COMPAT_HOME" "$PHASE7_PYTHON" "$TOOLS_ROOT/main_preflight.py" \
        --repo-root "$REPO_ROOT" --output-root "$preflight" \
        > "$root/preflight.stdout.log" 2> "$root/preflight.stderr.log"
    derived="$preflight/derived_bundle/phase7_holdout_canonical_v1.py"
    require_sha "$derived" "$EXPECTED_DERIVED_SHA" "DERIVED_RUNNER"

    echo "REPLAY_STAGE=4-seed-80-trial"
    HOME="$COMPAT_HOME" \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    "$PHASE7_PYTHON" "$derived" \
        --development "$DEVELOPMENT" \
        --canonical "$CANONICAL_PATH" \
        --phase6c-root "$PHASE6C_DIR" \
        --artifacts "$artifacts" \
        --freeze-sha256 "$EXPECTED_FREEZE_SHA" \
        --git-commit "$SCIENTIFIC_GIT_COMMIT" \
        --stop-after-replay \
        > "$root/replay.stdout.log" 2> "$root/replay.stderr.log" &
    pid=$!

    while kill -0 "$pid" 2>/dev/null; do
        done=0
        if [[ -f "$artifacts/progress.json" ]]; then
            done="$($PHASE7_PYTHON - "$artifacts/progress.json" <<'PY' 2>/dev/null || echo 0
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
print(int(data.get("replay_components_done", 0)))
PY
)"
        fi
        progress_bar "$done" 4 "Linux replay components=$done/4"
        sleep 2
    done
    wait "$pid" || rc=$?
    rc="${rc:-0}"
    printf '\n'
    echo "REPLAY_RC=$rc"
    if [[ "$rc" -ne 0 ]]; then
        tail -n 80 "$root/replay.stdout.log" || true
        tail -n 120 "$root/replay.stderr.log" || true
        fail "Linux Replay-only execution failed; Holdout remains blocked"
    fi

    verify_replay_artifacts "$artifacts" "$root"
    echo "LINUX_REPLAY_ROOT=$root"
    echo "SAFE_TO_EXECUTE_HOLDOUT_ON_LINUX=YES"
}

replay_cert_valid() {
    [[ -f "$REPLAY_CERT" ]] || return 1
    local head
    head="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    "$PHASE7_PYTHON" - "$REPLAY_CERT" "$head" "$EXPECTED_FREEZE_SHA" "$EXPECTED_DEV_SHA" "$EXPECTED_CANONICAL_SHA" <<'PY' >/dev/null
import json, sys
from importlib.metadata import version
from pathlib import Path

cert = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
head, freeze_sha, dev_sha, canonical_sha = sys.argv[2:6]
expected_runtime = {
    "mlforecast": "1.1.0",
    "optuna": "4.9.0",
    "catboost": "1.2.10",
    "pandas": "2.3.3",
    "numpy": "2.5.2",
    "scikit-learn": "1.9.0",
}
checks = [
    cert.get("status") == "PASS",
    cert.get("repo_head") == head,
    cert.get("candidate_freeze_sha256") == freeze_sha,
    cert.get("development_sha256") == dev_sha,
    cert.get("canonical_sha256") == canonical_sha,
    int(cert.get("components_verified", -1)) == 4,
    int(cert.get("verification_trial_count", -1)) == 80,
    int(cert.get("holdout_draws_accessed", -1)) == 0,
    int(cert.get("actuals_accessed", -1)) == 0,
    cert.get("holdout_executed") is False,
    cert.get("runtime") == expected_runtime,
    all(version(k) == v for k, v in expected_runtime.items()),
]
raise SystemExit(0 if all(checks) else 1)
PY
}

run_holdout() {
    if ! replay_cert_valid; then
        echo "LINUX_REPLAY_CERT=NOT_CURRENT"
        echo "ACTION=AUTO_REPLAY_BEFORE_HOLDOUT"
        run_replay
    else
        echo "LINUX_REPLAY_CERT=PASS_CURRENT"
    fi

    local stamp root pid rc done actuals
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    root="$COMPAT_DOWNLOADS/phase7-sealed-holdout-v1-$stamp"
    echo "HOLDOUT_ROOT=$root"
    echo "HOLDOUT_STAGE=sealed-50-draw"

    HOME="$COMPAT_HOME" \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    "$PHASE7_PYTHON" "$TOOLS_ROOT/sealed_holdout_execution.py" \
        --repo-root "$REPO_ROOT" \
        --output-root "$root" \
        > "$RUNTIME_ROOT/holdout-launcher.stdout.log" \
        2> "$RUNTIME_ROOT/holdout-launcher.stderr.log" &
    pid=$!

    while kill -0 "$pid" 2>/dev/null; do
        done=0
        actuals=0
        if [[ -f "$root/artifacts/progress.json" ]]; then
            read -r done actuals < <("$PHASE7_PYTHON" - "$root/artifacts/progress.json" <<'PY' 2>/dev/null || echo "0 0"
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
print(int(data.get("holdout_draws_done", 0)), int(data.get("actuals_accessed", 0)))
PY
)
        fi
        progress_bar "$done" "$EXPECTED_DRAWS" "Holdout=$done/50 Actuals=$actuals/50"
        sleep 2
    done
    wait "$pid" || rc=$?
    rc="${rc:-0}"
    printf '\n'
    echo "HOLDOUT_WRAPPER_RC=$rc"
    cat "$RUNTIME_ROOT/holdout-launcher.stdout.log" 2>/dev/null || true
    if [[ "$rc" -ne 0 ]]; then
        tail -n 120 "$RUNTIME_ROOT/holdout-launcher.stderr.log" 2>/dev/null || true
        if [[ -f "$root/RUNNER_TERMINAL_STATE.json" ]]; then
            echo "=== RUNNER_TERMINAL_STATE ==="
            cat "$root/RUNNER_TERMINAL_STATE.json"
        fi
        fail "sealed Holdout stopped; do not rerun if terminal state reports locks or actual access"
    fi
    echo "LINUX_HOLDOUT_STATUS=PASS"
}

show_status() {
    echo "PHASE7_LINUX_LAUNCHER=v1"
    echo "REPO_ROOT=$REPO_ROOT"
    echo "REPO_HEAD=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
    echo "EVIDENCE_ROOT=$EVIDENCE_ROOT"
    echo "RUNTIME_ROOT=$RUNTIME_ROOT"
    echo "PYTHON_VERSION=$PYTHON_VERSION"
    if [[ -d "$EVIDENCE_ROOT" ]]; then
        echo "EVIDENCE_ROOT_PRESENT=YES"
    else
        echo "EVIDENCE_ROOT_PRESENT=NO"
    fi
    if [[ -f "$REPLAY_CERT" ]]; then
        echo "LINUX_REPLAY_CERT_PRESENT=YES"
    else
        echo "LINUX_REPLAY_CERT_PRESENT=NO"
    fi
    echo "HOLDOUT_EXECUTED_BY_STATUS=NO"
}

case "$MODE" in
    status)
        show_status
        ;;
    runtime)
        verify_evidence
        prepare_compat_home
        ensure_runtime
        verify_repo
        echo "STATUS=PASS"
        echo "HOLDOUT_EXECUTED=NO"
        ;;
    preflight)
        verify_evidence
        prepare_compat_home
        ensure_runtime
        verify_repo
        run_preflight
        ;;
    replay)
        verify_evidence
        prepare_compat_home
        ensure_runtime
        verify_repo
        run_replay
        ;;
    holdout)
        verify_evidence
        prepare_compat_home
        ensure_runtime
        verify_repo
        run_holdout
        ;;
    *)
        echo "Usage: bash tools/phase7.sh {status|runtime|preflight|replay|holdout}"
        exit 2
        ;;
esac
