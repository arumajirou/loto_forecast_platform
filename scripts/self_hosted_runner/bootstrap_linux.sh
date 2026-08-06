#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="${REPOSITORY_URL:-https://github.com/arumajirou/loto_forecast_platform}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner-loto}"
RUNNER_NAME="${RUNNER_NAME:-$(hostname)-loto-gpu}"
RUNNER_LABELS="${RUNNER_LABELS:-loto-ci,gpu,cuda}"
RUNNER_WORK="${RUNNER_WORK:-_work}"
INSTALL_SERVICE="${INSTALL_SERVICE:-1}"
REQUIRE_CUDA="${REQUIRE_CUDA:-1}"
PAUSE_ON_EXIT="${PAUSE_ON_EXIT:-1}"
ALLOW_REPLACE="${ALLOW_REPLACE:-0}"

mkdir -p "$RUNNER_DIR/_setup_logs"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
LOG_FILE="$RUNNER_DIR/_setup_logs/bootstrap-$RUN_ID.log"
EXIT_FILE="$RUNNER_DIR/_setup_logs/bootstrap-$RUN_ID.exitcode"

finish() {
  local rc=$?
  printf '%s\n' "$rc" > "$EXIT_FILE"
  printf '\nstatus=%s\nlog=%s\nexit_code_file=%s\n' \
    "$([[ $rc -eq 0 ]] && echo VERIFIED || echo FAILED)" \
    "$LOG_FILE" \
    "$EXIT_FILE"
  if [[ -t 0 && "$PAUSE_ON_EXIT" == "1" ]]; then
    read -r -p "Enterキーで終了します..." _ || true
  fi
  exit "$rc"
}
trap finish EXIT
exec > >(tee -a "$LOG_FILE") 2>&1

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  echo "FAILED: rootでは実行せず、専用の非管理者Runnerユーザーで実行してください。"
  exit 10
fi

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "FAILED: このスクリプトはLinux x86_64専用です。"
  exit 11
fi

for command in curl tar sha256sum git uv; do
  command -v "$command" >/dev/null || {
    echo "FAILED: required command not found: $command"
    exit 12
  }
done

if [[ "$REQUIRE_CUDA" == "1" ]]; then
  command -v nvidia-smi >/dev/null || {
    echo "FAILED: nvidia-smi is required for the cuda label."
    exit 13
  }
  nvidia-smi
fi

curl --fail --silent --show-error --location --head https://github.com >/dev/null
curl --fail --silent --show-error --location --head https://api.github.com >/dev/null

if [[ -z "${RUNNER_DOWNLOAD_URL:-}" ]]; then
  echo "FAILED: RUNNER_DOWNLOAD_URLを設定してください。"
  echo "GitHub > Settings > Actions > Runners > New self-hosted runner に表示されるURLを使用します。"
  exit 20
fi
if [[ -z "${RUNNER_SHA256:-}" ]]; then
  echo "FAILED: RUNNER_SHA256を設定してください。GitHub画面に表示されるSHA-256を使用します。"
  exit 21
fi
if [[ -z "${RUNNER_TOKEN:-}" ]]; then
  if [[ -t 0 ]]; then
    read -r -s -p "GitHubの1時間有効なRunner登録token: " RUNNER_TOKEN
    printf '\n'
  else
    echo "FAILED: RUNNER_TOKEN is required in non-interactive mode."
    exit 22
  fi
fi

if [[ -f "$RUNNER_DIR/.runner" && "$ALLOW_REPLACE" != "1" ]]; then
  echo "BLOCKED: $RUNNER_DIR は既に登録済みです。置換する場合だけ ALLOW_REPLACE=1 を設定してください。"
  exit 23
fi

archive="$RUNNER_DIR/actions-runner.tar.gz"
curl --fail --location --proto '=https' --tlsv1.2 \
  "$RUNNER_DOWNLOAD_URL" \
  --output "$archive"
printf '%s  %s\n' "$RUNNER_SHA256" "$archive" | sha256sum --check --strict

tar --extract --gzip --file "$archive" --directory "$RUNNER_DIR"
rm -f "$archive"

cd "$RUNNER_DIR"
config_args=(
  --unattended
  --url "$REPOSITORY_URL"
  --token "$RUNNER_TOKEN"
  --name "$RUNNER_NAME"
  --work "$RUNNER_WORK"
  --labels "$RUNNER_LABELS"
)
if [[ "$ALLOW_REPLACE" == "1" ]]; then
  config_args+=(--replace)
fi
./config.sh "${config_args[@]}"
unset RUNNER_TOKEN

if [[ "$INSTALL_SERVICE" == "1" ]]; then
  sudo ./svc.sh install "$USER"
  sudo ./svc.sh start
  sudo ./svc.sh status
else
  echo "EXECUTION_PENDING: サービス未導入です。対話実行は $RUNNER_DIR/run.sh"
fi

echo "VERIFIED: Runner登録処理が完了しました。"
echo "labels=self-hosted,linux,x64,$RUNNER_LABELS"
echo "次にGitHubのActions > RunnersでIdle/Onlineを確認してください。"
