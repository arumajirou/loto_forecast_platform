#!/usr/bin/env bash
# MTP起動条件をdry-runで表示するスクリプト
#
# 使用法:
#   scripts/print_mtp_condition.sh A
#   scripts/print_mtp_condition.sh B
#
# 初期状態ではサーバーを起動せず、コマンドを表示するだけにしてください。

set -euo pipefail

CONDITION="${1:-}"

if [[ "$CONDITION" != "A" && "$CONDITION" != "B" ]]; then
  echo "Usage: $0 <A|B>" >&2
  exit 1
fi

# サーバーバイナリ
SERVER_BIN="/usr/local/bin/llama-server"

# モデル
MODEL="/mnt/e/models/ornith35b-v0.1.0.Q4_K_M.gguf"
MTP_MODEL=""

# MTP関連引数
MTP_ARGS=""
DRAFT_N=0

case "$CONDITION" in
  A)
    # Condition A: MTP完全無効
    MTP_ARGS=""
    DRAFT_N=0
    echo "Condition A: MTP完全無効"
    ;;
  B)
    # Condition B: MTP有効
    MTP_MODEL="/mnt/e/models/ornith35b-draft.Q4_K_M.gguf"
    DRAFT_N=2
    MTP_ARGS="--mtp --mtp-draft-model $MTP_MODEL --mtp-n-draft $DRAFT_N"
    echo "Condition B: MTP有効"
    ;;
esac

# ポート
PORT=17210

# context/batch/ubatch
CONTEXT=8192
BATCH=128
UBATCH=128

# log/pid
LOG=".ai/runtime/phase17/mtp_${CONDITION}.log"
PID_FILE=".ai/runtime/phase17/mtp_${CONDITION}.pid"

# 安全にquote
quote() {
  printf '%q' "$1"
}

# 完全コマンドを構築
FULL_CMD="\"${SERVER_BIN}\" --model \"${MODEL}\" --port ${PORT} --ctx-size ${CONTEXT} --batch-size ${BATCH} --ubatch-size ${UBATCH}"

if [[ "$CONDITION" == "B" ]]; then
  FULL_CMD="${FULL_CMD} --mtp --mtp-draft-model \"${MTP_MODEL}\" --mtp-n-draft ${DRAFT_N}"
fi

echo "condition: ${CONDITION}"
echo "server_binary: ${SERVER_BIN}"
echo "server_version: $(\"${SERVER_BIN}\" --version 2>&1 || echo 'unknown')"
echo "target_model: ${MODEL}"
echo "target_sha256: $(sha256sum "${MODEL}" | cut -d' ' -f1)"
echo "mtp_model: ${MTP_MODEL:-none}"
echo "mtp_sha256: $(sha256sum "${MTP_MODEL}" 2>/dev/null || echo 'none')"
echo "port: ${PORT}"
echo "context: ${CONTEXT}"
echo "batch: ${BATCH}"
echo "ubatch: ${UBATCH}"
echo "full_command: ${FULL_CMD}"
echo "log: ${LOG}"
echo "pid_file: ${PID_FILE}"
