#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT=""
REQUEST=""
OUTPUT_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="$2"
      shift 2
      ;;
    --request)
      REQUEST="$2"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$REPO_ROOT" || -z "$REQUEST" || -z "$OUTPUT_ROOT" ]]; then
  echo "Required: --repo-root --request --output-root" >&2
  exit 2
fi

cd "$REPO_ROOT"

PYTHONDONTWRITEBYTECODE=1 \
uv run --frozen --extra full python -m \
  loto.neuralforecast.auto_frets.certify run \
  --request "$REQUEST" \
  --output-root "$OUTPUT_ROOT"

if [[ "${LOTO_NO_WAIT:-0}" != "1" ]]; then
  read -r -p "Enterキーで終了します..." _
fi
