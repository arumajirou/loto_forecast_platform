# Sundial provider v2 evidence handoff

## Status

`VERIFIER_IMPLEMENTED / TARGET_HOST_EVIDENCE_PENDING`

The certification run is not accepted from `status.txt` alone. The verifier recomputes and checks
the entire evidence contract before producing a shareable ZIP.

## Verification gates

- every file except `SHA256SUMS` is covered exactly once by SHA-256;
- absolute paths, parent traversal, duplicate checksum rows, and symlinked evidence are rejected;
- Run ID, repository ID, revision, sample matrix, seed, case ordering, and manifest agree;
- all CPU and CUDA cases passed with no timeout or non-zero return code;
- each request and response hash agrees with its case summary;
- CUDA cases prove internal and external PID/VRAM evidence and forbid CPU fallback;
- raw samples and point predictions are finite and have the expected shape;
- replay classification is recomputed from the two response files;
- the checked-out runner, harness, lockfile, and remote-code review hashes match the run;
- an optional expected Git commit and branch can be required.

## Package command

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

git switch feat/sundial-probabilistic-provider-v2
EXPECTED_COMMIT="$(git rev-parse HEAD)"

bash scripts/package_sundial_provider_v2_evidence.sh \
  /mnt/e/env/ts/loto_forecast_platform \
  "$(cat artifacts/sundial-provider-v2/LATEST)" \
  "$EXPECTED_COMMIT"
```

The command produces:

```text
artifacts/sundial-provider-v2-verified/<RUN_ID>/VERIFICATION_REPORT.json
artifacts/sundial-provider-v2-verified/<RUN_ID>/VERIFICATION_REPORT.md
artifacts/sundial-provider-v2-verified/<RUN_ID>/PR_COMMENT.md
artifacts/sundial-provider-v2-verified/<RUN_ID>-evidence.zip
artifacts/sundial-provider-v2-verified/<RUN_ID>-evidence.zip.sha256
```

Only `SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=PASS` is acceptable for formal review. A
certification `PASS` with a verifier `FAIL` or `BLOCKED` remains non-certified.
