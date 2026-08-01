#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${REF:-b9f1c246d5ae28499d2d51def06a9c352b0976a3}"
BASE="https://raw.githubusercontent.com/arumajirou/loto_forecast_platform/$REF/src/loto/data"
DEST="$ROOT/src/loto/data"
mkdir -p "$DEST"
files=(__init__.py canonical.py datasets.py fetcher.py integrated.py lineage.py lotteries.py parser.py provenance.py robots.py)
for file in "${files[@]}"; do
  if [[ ! -s "$DEST/$file" ]]; then
    curl -fL --retry 3 --connect-timeout 20 "$BASE/$file" -o "$DEST/$file"
  fi
done
python -m compileall -q "$DEST"
echo "PASS: restored src/loto/data from $REF"
