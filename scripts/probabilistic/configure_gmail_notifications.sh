#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(pwd)}"
ENV_FILE="$ROOT/.env.ppl-notify"
EMAIL="zakumagahiyakesita@gmail.com"

cat <<'EOF'
Gmailの通常パスワードは使用しません。
Googleアカウントの2段階認証を有効にして、アプリパスワードを作成してください。
表示された16文字を空白込みで貼り付けても、保存時に空白を除去します。
EOF

read -r -p "SMTP username [$EMAIL]: " USERNAME
USERNAME="${USERNAME:-$EMAIL}"
read -r -s -p "Gmail app password: " RAW_PASSWORD
echo
APP_PASSWORD="$(printf '%s' "$RAW_PASSWORD" | tr -d '[:space:]')"

if test -z "$APP_PASSWORD"; then
    echo "ERROR: app password is empty" >&2
    exit 2
fi
if test "${#APP_PASSWORD}" -ne 16; then
    echo "WARNING: Gmail app password is normally 16 characters; got ${#APP_PASSWORD}." >&2
fi

umask 077
{
    printf 'export LOTO_SMTP_USERNAME=%q\n' "$USERNAME"
    printf 'export LOTO_SMTP_APP_PASSWORD=%q\n' "$APP_PASSWORD"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "CREATED=$ENV_FILE"
echo "APP_PASSWORD_LENGTH=${#APP_PASSWORD}"
echo "Load with: source '$ENV_FILE'"
echo "Test with: uv run python scripts/probabilistic/test_notifications.py --email"
