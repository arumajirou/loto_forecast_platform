#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.env.ppl-api"
BASE="http://${LOTO_PPL_API_HOST:-127.0.0.1}:${LOTO_PPL_API_PORT:-8765}"
AUTH="Authorization: Bearer $LOTO_PPL_API_TOKEN"

echo "=== health ==="
curl -fsS "$BASE/health" | python3 -m json.tool

echo "=== profiles ==="
curl -fsS -H "$AUTH" "$BASE/api/v1/profiles" | python3 -m json.tool

echo "=== VOICEVOX status ==="
curl -fsS -H "$AUTH" "$BASE/api/v1/tts/status" | python3 -m json.tool

echo
cat <<EOF
日本語音声をサーバー上で再生:
curl -fsS -X POST \\
  -H '$AUTH' \\
  -H 'Content-Type: application/json' \\
  '$BASE/api/v1/tts/play' \\
  -d '{"text":"確率モデルの進捗は25パーセントです","speaker":3,"speed_scale":1.15}' \\
  | python3 -m json.tool

日本語音声をWAVとして保存:
curl -fsS -X POST \\
  -H '$AUTH' \\
  -H 'Content-Type: application/json' \\
  '$BASE/api/v1/tts/synthesize' \\
  -d '{"text":"音声APIのテストです","speaker":3}' \\
  -o /tmp/loto-ppl-speech.wav

JAX CUDA修復前にCPU fast runを開始:
curl -fsS -X POST \\
  -H '$AUTH' \\
  -H 'Content-Type: application/json' \\
  '$BASE/api/v1/runs' \\
  -d '{"profile":"fast_cpu","preflight":false,"overrides":{"email_enabled":false}}' \\
  | python3 -m json.tool

JAX CUDA修復後にGPU fast runを開始:
curl -fsS -X POST \\
  -H '$AUTH' \\
  -H 'Content-Type: application/json' \\
  '$BASE/api/v1/runs' \\
  -d '{"profile":"fast_gpu","preflight":true,"overrides":{"email_enabled":false}}' \\
  | python3 -m json.tool

現在の進捗:
curl -fsS -H '$AUTH' '$BASE/api/v1/runs/current' | python3 -m json.tool

SSE進捗ストリーム:
curl -N -H '$AUTH' '$BASE/api/v1/runs/<RUN_ID>/events'
EOF
