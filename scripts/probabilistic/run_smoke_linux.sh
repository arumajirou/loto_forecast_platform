#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${ROOT}"
uv run loto3 probabilistic smoke --config configs/probabilistic/smoke.yaml
