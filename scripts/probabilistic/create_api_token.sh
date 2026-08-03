#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT"
TARGET="$ROOT/.env.ppl-api"
if test -f "$TARGET"; then
    echo "EXISTS=$TARGET"
    echo "既存トークンを変更する場合はファイルを退避して再実行してください。"
    exit 0
fi
TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
umask 077
cat > "$TARGET" <<EOF
export LOTO_PPL_ROOT='$ROOT'
export LOTO_PPL_API_TOKEN='$TOKEN'
export LOTO_PPL_API_HOST='127.0.0.1'
export LOTO_PPL_API_PORT='8765'
export LOTO_VOICEVOX_URL='http://127.0.0.1:50021'
EOF
chmod 600 "$TARGET"
echo "CREATED=$TARGET"
echo "TOKEN=$TOKEN"
echo "このトークンは安全な場所に保管し、Gitやチャットへ貼り付けないでください。"
