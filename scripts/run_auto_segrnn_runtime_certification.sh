#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage:
  run_auto_segrnn_runtime_certification.sh \
    --repo-root /absolute/repository \
    --request /absolute/request.json \
    --output-root /absolute/output-directory
EOF
}

REPO_ROOT=""
REQUEST=""
OUTPUT_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --request) REQUEST="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$REPO_ROOT" || -z "$REQUEST" || -z "$OUTPUT_ROOT" ]]; then
  usage >&2
  exit 2
fi

REPO_ROOT="$(realpath "$REPO_ROOT")"
REQUEST="$(realpath "$REQUEST")"
if [[ "$OUTPUT_ROOT" != /* ]]; then
  echo "--output-root must be absolute" >&2
  exit 2
fi

cd "$REPO_ROOT"
export PYTHONDONTWRITEBYTECODE=1
uv run --frozen --extra full python -m \
  loto.neuralforecast.auto_segrnn.certify run \
  --request "$REQUEST" \
  --output-root "$OUTPUT_ROOT"

if [[ "${LOTO_NO_WAIT:-0}" != "1" ]]; then
  read -r -p "Enterキーで終了します..." _
fi
