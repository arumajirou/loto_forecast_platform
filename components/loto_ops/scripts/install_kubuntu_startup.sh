#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/install_user_services.sh" "${1:-06:30}" "${2:-8520}"
