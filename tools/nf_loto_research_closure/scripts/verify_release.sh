#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE="${1:?Usage: $0 RELEASE_DIRECTORY}"
cd "$ROOT"
uv run loto-research verify "$PACKAGE"
