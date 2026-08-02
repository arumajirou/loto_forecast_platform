#!/usr/bin/env bash
set -euo pipefail
SOURCE="${1:-/mnt/e/env/ts/loto_ops_pipeline-fixed-20260729-v2}"
TARGET="${2:-/mnt/e/env/ts/loto_ops}"
STAMP="$(date +%Y%m%d_%H%M%S)"

if [[ ! -d "$SOURCE" ]]; then
    echo "ERROR: source does not exist: $SOURCE" >&2
    exit 2
fi
if [[ -e "$TARGET" ]]; then
    echo "ERROR: target already exists: $TARGET" >&2
    exit 3
fi
mkdir -p "$TARGET"
rsync -a --exclude='.venv/' --exclude='__pycache__/' "$SOURCE/" "$TARGET/"
find "$TARGET" -type d -name __pycache__ -prune -exec rm -rf {} +

cat <<INFO
Copied to short directory:
  $TARGET
Original remains unchanged:
  $SOURCE
Next:
  cd $TARGET
  bash setup_linux.sh
  bash install_automation.sh
After verification, archive the original as:
  mv $SOURCE ${SOURCE}.bak.$STAMP
INFO
