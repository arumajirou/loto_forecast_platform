#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$HOME/.config/loto-ops"
ENV_FILE="$CONFIG_DIR/runtime.env"
PGPASS="$HOME/.pgpass"
mkdir -p "$CONFIG_DIR"

read -rp "PostgreSQL host [127.0.0.1]: " DB_HOST_INPUT
DB_HOST_VALUE="${DB_HOST_INPUT:-127.0.0.1}"
read -rp "PostgreSQL port [5432]: " DB_PORT_INPUT
DB_PORT_VALUE="${DB_PORT_INPUT:-5432}"
read -rp "PostgreSQL user [loto]: " DB_USER_INPUT
DB_USER_VALUE="${DB_USER_INPUT:-loto}"
read -rp "PostgreSQL database [loto]: " DB_NAME_INPUT
DB_NAME_VALUE="${DB_NAME_INPUT:-loto}"
read -rsp "PostgreSQL password: " DB_PASSWORD_VALUE
echo

read -rp "Gmail address (sender): " GMAIL_USER
read -rsp "Gmail app password (16 characters): " GMAIL_APP_PASSWORD
echo
GMAIL_APP_PASSWORD="${GMAIL_APP_PASSWORD// /}"
read -rp "Notification recipient [$GMAIL_USER]: " EMAIL_TO_INPUT
EMAIL_TO_VALUE="${EMAIL_TO_INPUT:-$GMAIL_USER}"
read -rsp "Slack incoming webhook URL: " SLACK_WEBHOOK
echo

if [[ -z "$DB_PASSWORD_VALUE" || -z "$GMAIL_USER" || -z "$GMAIL_APP_PASSWORD" || -z "$SLACK_WEBHOOK" ]]; then
    echo "ERROR: DB password, Gmail, Gmail app password, and Slack webhook are required." >&2
    exit 2
fi

if [[ "$SLACK_WEBHOOK" != https://hooks.slack.com/services/* ]]; then
    echo "WARNING: Slack URL does not look like an incoming webhook URL." >&2
fi

quote_env() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
}

TMP="$(mktemp "$CONFIG_DIR/runtime.env.XXXXXX")"
{
    printf 'LOTO_OPS_PROJECT=%s\n' "$(quote_env "$ROOT")"
    printf 'LOTO_OPS_CONFIG=%s\n' "$(quote_env "$ROOT/configs/loto_ops.yaml")"
    printf 'LOTO_LIFE_PROJECT=%s\n' "$(quote_env "/mnt/e/env/ts/loto_life_feature_pipeline")"
    printf 'LOTO_FORECAST_PROJECT=%s\n' "$(quote_env "/mnt/e/env/ts/loto_neuralforecast_pipeline")"
    printf 'LOTO_ZIP_OUTPUT_DIR=%s\n' "$(quote_env "/mnt/e/env/ts/zips")"
    printf 'LOTO_OPS_MODE=%s\n' "$(quote_env "light")"
    printf 'DB_HOST=%s\n' "$(quote_env "$DB_HOST_VALUE")"
    printf 'DB_PORT=%s\n' "$(quote_env "$DB_PORT_VALUE")"
    printf 'DB_USER=%s\n' "$(quote_env "$DB_USER_VALUE")"
    printf 'DB_PASSWORD=%s\n' "$(quote_env "$DB_PASSWORD_VALUE")"
    printf 'DB_NAME=%s\n' "$(quote_env "$DB_NAME_VALUE")"
    printf 'LOTO_NOTIFY_ENABLED=1\n'
    printf 'LOTO_NOTIFY_ON_SUCCESS=1\n'
    printf 'LOTO_NOTIFY_ON_FAILURE=1\n'
    printf 'LOTO_NOTIFY_EMAIL_ENABLED=1\n'
    printf 'LOTO_NOTIFY_EMAIL_TO=%s\n' "$(quote_env "$EMAIL_TO_VALUE")"
    printf 'LOTO_NOTIFY_EMAIL_FROM=%s\n' "$(quote_env "$GMAIL_USER")"
    printf 'LOTO_NOTIFY_SMTP_HOST=%s\n' "$(quote_env "smtp.gmail.com")"
    printf 'LOTO_NOTIFY_SMTP_PORT=587\n'
    printf 'LOTO_NOTIFY_SMTP_STARTTLS=1\n'
    printf 'LOTO_NOTIFY_SMTP_USER=%s\n' "$(quote_env "$GMAIL_USER")"
    printf 'LOTO_NOTIFY_SMTP_PASSWORD=%s\n' "$(quote_env "$GMAIL_APP_PASSWORD")"
    printf 'LOTO_NOTIFY_SLACK_ENABLED=1\n'
    printf 'LOTO_NOTIFY_SLACK_WEBHOOK_URL=%s\n' "$(quote_env "$SLACK_WEBHOOK")"
} > "$TMP"
chmod 600 "$TMP"
mv -f "$TMP" "$ENV_FILE"

# PostgreSQL CLI uses .pgpass, while Python/systemd uses runtime.env.
printf '%s:%s:%s:%s:%s\n' \
    "$DB_HOST_VALUE" "$DB_PORT_VALUE" "$DB_NAME_VALUE" "$DB_USER_VALUE" "$DB_PASSWORD_VALUE" \
    > "$PGPASS"
chmod 600 "$PGPASS"

unset DB_PASSWORD_VALUE GMAIL_APP_PASSWORD SLACK_WEBHOOK

echo "Created: $ENV_FILE (mode 600)"
echo "Created: $PGPASS (mode 600)"
echo "Test: $ROOT/scripts/test_notifications.sh"
