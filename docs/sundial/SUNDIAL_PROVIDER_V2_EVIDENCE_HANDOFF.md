# Sundial provider v2 evidence handoff

## Status

`VERIFIER_IMPLEMENTED / SEMANTIC_ARCHIVE_CONTRACT_READY / TARGET_HOST_EVIDENCE_PENDING`

The certification run is not accepted from `status.txt` alone. The verifier recomputes and checks
the entire evidence contract before producing a shareable ZIP.

## Verification gates

- every run file except `SHA256SUMS` is covered exactly once by SHA-256;
- absolute paths, parent traversal, duplicate checksum rows, and symlinked evidence are rejected;
- Run ID, repository ID, revision, sample matrix, seed, case ordering, and manifest agree;
- all CPU and CUDA cases passed with no timeout or non-zero return code;
- each request and response hash agrees with its case summary;
- CUDA cases prove internal and external PID/VRAM evidence and forbid CPU fallback;
- raw samples and point predictions are finite and have the expected shape;
- replay classification is recomputed from the two response files;
- the checked-out runner, harness, lockfile, and remote-code review hashes match the run;
- the independent semantic report is required, hashed, and embedded in the evidence ZIP;
- an optional expected Git commit and branch can be required.

A missing or symlinked `status.txt` returns a structured verification result with
`status=FAIL` and `reason=STATUS_FILE_MISSING`. It is not surfaced as an unclassified file-read
exception.

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

The launcher runs semantic verification first and then passes the generated report to the evidence
verifier with `--semantic-report`. It also opens the completed ZIP and checks for the semantic entry.

The command produces:

```text
artifacts/sundial-provider-v2-semantic-verification/<RUN_ID>.json
artifacts/sundial-provider-v2-verified/<RUN_ID>/VERIFICATION_REPORT.json
artifacts/sundial-provider-v2-verified/<RUN_ID>/VERIFICATION_REPORT.md
artifacts/sundial-provider-v2-verified/<RUN_ID>/PR_COMMENT.md
artifacts/sundial-provider-v2-verified/<RUN_ID>-evidence.zip
artifacts/sundial-provider-v2-verified/<RUN_ID>-evidence.zip.sha256
```

The ZIP includes:

```text
run/**
verification/**
semantic/<RUN_ID>.json
```

Only `SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=PASS` is acceptable for formal review. A
certification `PASS` with a semantic or evidence verifier `FAIL` or `BLOCKED` remains non-certified.
