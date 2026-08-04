#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(
  cd "$(dirname "$0")/../.." &&
  pwd
)"

cd "${ROOT}"

CONFIG_DIR="${TCN_CONFIG_DIR:-configs/generated/tcn-v2/screening}"
LOG_DIR="${TCN_LOG_DIR:-artifacts/numbers3/tcn-v2-screening-parallel-logs}"
STATUS_DIR="${LOG_DIR}/status"
WORKERS="${TCN_WORKERS:-4}"

mkdir -p \
  "${LOG_DIR}" \
  "${STATUS_DIR}"

mapfile -t CONFIGS < <(
  find "${CONFIG_DIR}" \
    -maxdepth 1 \
    -type f \
    -name '*.yaml' \
    -print |
  sort
)

if [[ "${#CONFIGS[@]}" -eq 0 ]]
then
  echo "ERROR: no configs found in ${CONFIG_DIR}" >&2
  exit 1
fi

printf '%s\0' "${CONFIGS[@]}" |
xargs \
  -0 \
  -r \
  -P "${WORKERS}" \
  -I '__CONFIG__' \
  bash -c '
    set -Eeuo pipefail

    config="$1"
    log_dir="$2"
    status_dir="$3"

    name="$(basename "${config}" .yaml)"
    log="${log_dir}/${name}.log"
    status="${status_dir}/${name}.status"

    {
      echo "RUNNING"
      echo "shell_pid=$$"
      echo "started_at=$(date --iso-8601=seconds)"
      echo "config=${config}"
      echo "log=${log}"
    } > "${status}"

    set +e

    CUDA_VISIBLE_DEVICES=0 \
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4 \
    NUMEXPR_NUM_THREADS=4 \
    uv run python \
      scripts/experiments/run_numbers3_n1_tcn_exhaustive.py \
      --config "${config}" \
      --mode evaluate \
      --skip-model-artifacts \
      > "${log}" 2>&1

    rc=$?

    set -e

    {
      if [[ "${rc}" -eq 0 ]]
      then
        echo "PASS"
      else
        echo "FAIL"
      fi

      echo "exit_code=${rc}"
      echo "finished_at=$(date --iso-8601=seconds)"
      echo "config=${config}"
      echo "log=${log}"
    } > "${status}"

    exit "${rc}"
  ' _ \
  '__CONFIG__' \
  "${LOG_DIR}" \
  "${STATUS_DIR}"
