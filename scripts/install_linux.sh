#!/usr/bin/env bash
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-/mnt/e/env/ts/loto}"
mkdir -p "$DEST"
rsync -a --delete --exclude '.venv' --exclude 'runs' "$SRC/" "$DEST/"
cd "$DEST"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[api]'
mkdir -p data runs "$HOME/.config/loto" "$HOME/.config/systemd/user"
[ -f "$HOME/.config/loto/runtime.env" ] || cp .env.example "$HOME/.config/loto/runtime.env"
cp deploy/systemd/*.service deploy/systemd/*.timer "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
printf 'Installed to %s\nEdit %s before enabling services.\n' "$DEST" "$HOME/.config/loto/runtime.env"
