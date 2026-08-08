#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

EXPECTED_UUID="77f73394-4477-4713-bebf-90e94dc1f89e"
MOUNTPOINT="/mnt/e"
REPO_ROOT="$(git rev-parse --show-toplevel)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUNTIME_ROOT="${MOUNTPOINT}/env/ts/.wsl-physical-ext4-bench-runtime-${STAMP}-$$"

cleanup() {
  local rc=$?
  set +e
  rm -rf "$RUNTIME_ROOT" >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT

echo "=== WSL physical-ext4 benchmark launcher ==="

if ! grep -Eqi 'microsoft|wsl' /proc/sys/kernel/osrelease /proc/version 2>/dev/null; then
  echo "STOP_REASON=NOT_WSL" >&2
  exit 10
fi

if ! mountpoint -q "$MOUNTPOINT"; then
  echo "STOP_REASON=PHYSICAL_EXT4_NOT_MOUNTED" >&2
  exit 11
fi

SOURCE="$(findmnt -n -o SOURCE "$MOUNTPOINT")"
FSTYPE="$(findmnt -n -o FSTYPE "$MOUNTPOINT")"
OPTIONS="$(findmnt -n -o OPTIONS "$MOUNTPOINT")"
UUID="$(lsblk -no UUID "$SOURCE" | head -n1 | tr -d '[:space:]')"
REPO_SOURCE="$(findmnt -n -T "$REPO_ROOT" -o SOURCE)"
REPO_FSTYPE="$(findmnt -n -T "$REPO_ROOT" -o FSTYPE)"

[[ "$FSTYPE" == "ext4" ]] || { echo "STOP_REASON=MOUNT_NOT_EXT4" >&2; exit 12; }
grep -Eq '(^|,)rw(,|$)' <<<"$OPTIONS" || { echo "STOP_REASON=MOUNT_NOT_RW" >&2; exit 13; }
[[ "$UUID" == "$EXPECTED_UUID" ]] || { echo "STOP_REASON=UNEXPECTED_EXT4_UUID:$UUID" >&2; exit 14; }
[[ "$REPO_SOURCE" == "$SOURCE" && "$REPO_FSTYPE" == "ext4" ]] || {
  echo "STOP_REASON=REPO_NOT_ON_PHYSICAL_EXT4" >&2
  exit 15
}

mkdir -p "$RUNTIME_ROOT/tmp" "$RUNTIME_ROOT/cache" "$RUNTIME_ROOT/python" "$RUNTIME_ROOT/bin"
export TMPDIR="$RUNTIME_ROOT/tmp"
export UV_CACHE_DIR="$RUNTIME_ROOT/cache"
export UV_PYTHON_INSTALL_DIR="$RUNTIME_ROOT/python"
export UV_PYTHON_BIN_DIR="$RUNTIME_ROOT/bin"

TMP_SOURCE="$(findmnt -n -T "$TMPDIR" -o SOURCE)"
CACHE_SOURCE="$(findmnt -n -T "$UV_CACHE_DIR" -o SOURCE)"
PYTHON_SOURCE="$(findmnt -n -T "$UV_PYTHON_INSTALL_DIR" -o SOURCE)"

[[ "$TMP_SOURCE" == "$SOURCE" ]] || { echo "STOP_REASON=TMPDIR_NOT_ON_PHYSICAL_EXT4" >&2; exit 16; }
[[ "$CACHE_SOURCE" == "$SOURCE" ]] || { echo "STOP_REASON=UV_CACHE_NOT_ON_PHYSICAL_EXT4" >&2; exit 17; }
[[ "$PYTHON_SOURCE" == "$SOURCE" ]] || { echo "STOP_REASON=UV_PYTHON_NOT_ON_PHYSICAL_EXT4" >&2; exit 18; }

echo "WSL_PHYSICAL_EXT4_PREFLIGHT=PASS"
echo "PHYSICAL_EXT4_SOURCE=$SOURCE"
echo "PHYSICAL_EXT4_UUID=$UUID"
echo "PHYSICAL_EXT4_MOUNTPOINT=$MOUNTPOINT"
echo "PHYSICAL_EXT4_OPTIONS=$OPTIONS"
echo "REPO_ROOT=$REPO_ROOT"
echo "REPO_FILESYSTEM=$REPO_FSTYPE"
echo "TMPDIR=$TMPDIR"
echo "UV_CACHE_DIR=$UV_CACHE_DIR"
echo "UV_PYTHON_INSTALL_DIR=$UV_PYTHON_INSTALL_DIR"
echo "UV_PYTHON_BIN_DIR=$UV_PYTHON_BIN_DIR"

echo "=== delegate to governed WSL benchmark wrapper ==="
bash "$REPO_ROOT/scripts/benchmarks/run_wsl_benchmark_and_push.sh"

echo "WSL_PHYSICAL_EXT4_BENCHMARK=PASS"
echo "STOP_REASON=NONE"
