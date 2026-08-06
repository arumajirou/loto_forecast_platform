# TimesFM 2.5 Evidence Review Runbook

## Input

Use the ZIP and sidecar created by P9 finalization:

```text
artifacts/timesfm25/runtime-archives/<run_id>.zip
artifacts/timesfm25/runtime-archives/<run_id>.zip.sha256
```

Do not unzip, edit, rename, or regenerate the source archive before review.

## Review command

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

RUN_ID="<the exact target-host run id>"
ARCHIVE="artifacts/timesfm25/runtime-archives/${RUN_ID}.zip"
SIDECAR="${ARCHIVE}.sha256"
OUTPUT_ROOT="artifacts/timesfm25/evidence-review"

uv run python scripts/review_timesfm25_evidence.py \
  --archive "$ARCHIVE" \
  --sha256 "$SIDECAR" \
  --expected-run-id "$RUN_ID" \
  --output-root "$OUTPUT_ROOT"

rc=$?
printf 'EXIT_CODE=%s\n' "$rc"
printf 'ARCHIVE=%s\n' "$ARCHIVE"
printf 'SIDECAR=%s\n' "$SIDECAR"
printf 'OUTPUT_ROOT=%s\n' "$OUTPUT_ROOT"
printf 'Enterキーで終了します...'
read -r _
exit "$rc"
```

## Exit codes

```text
0 = FORMAL_GPU_CERTIFIED or FORMAL_CPU_CERTIFIED
2 = PARTIALLY_VERIFIED_GPU; archived evidence is valid but not formally promoted
1 = rejected, unsafe, corrupt, mismatched, duplicate, or already-reviewed input
```

## Review output

```text
artifacts/timesfm25/evidence-review/<run_id>-<archive_sha_prefix>/
├── ARCHIVE_SHA256.txt
├── EVIDENCE_REVIEW.json
├── EVIDENCE_REVIEW.md
├── REVIEW_SHA256SUMS
└── bundle/
    └── <run_id>/
        ├── SHA256SUMS
        ├── preflight.json
        ├── provider_request.json
        ├── provider_response.json
        ├── runtime_certification.json
        └── ...
```

Verify the outer seal:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
REVIEW_DIR="artifacts/timesfm25/evidence-review/<review id>"

uv run python - "$REVIEW_DIR" <<'PY'
from pathlib import Path
import sys

from loto.timesfm25_campaign.certification_bundle import verify_sha256_manifest

root = Path(sys.argv[1])
ok, failures = verify_sha256_manifest(root, manifest_name="REVIEW_SHA256SUMS")
print(f"REVIEW_SHA256_VERIFY={'PASS' if ok else 'FAIL'}")
for failure in failures:
    print(f"FAILURE={failure}")
raise SystemExit(0 if ok else 1)
PY

printf 'Enterキーで終了します...'
read -r _
```

A partial review result must remain partial. Do not edit `EVIDENCE_REVIEW.json` or
manually replace `formal_status`.
