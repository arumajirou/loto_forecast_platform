# GluonTS P7D evidence handoff runbook

## Purpose

P7D turns one completed P7C orchestration directory into a self-verifying ZIP. It does not change,
repair, or reclassify the source evidence. The ZIP is intended for transfer to another machine or for
upload into a later review session.

## Run P7B, P7C, and P7D together

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

git fetch origin
git checkout feat/gluonts-probabilistic-contract-v1
git pull --ff-only origin feat/gluonts-probabilistic-contract-v1

RUN_ID="gluonts-p7d-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="/mnt/e/env/logs/${RUN_ID}"
ARCHIVE="${RUN_ROOT}.zip"

RUN_ID="${RUN_ID}" \
bash environments/gluonts-p7d-target-machine.sh \
  "${RUN_ROOT}" \
  "${ARCHIVE}"
```

Exit codes remain aligned with P7C:

```text
0   verified bundle and P8 eligible
10  verified bundle; valid evidence requires remediation
20  verified bundle; evidence is invalid or incomplete
2   execution, input, or bundle contract failure
```

## Export an existing completed P7C run

```bash
bash environments/gluonts-p7d-export.sh \
  "/mnt/e/env/logs/<P7C_RUN_ID>" \
  "/mnt/e/env/logs/<P7C_RUN_ID>.zip"
```

The exporter creates both the ZIP and `<archive>.sha256`, then immediately verifies the ZIP without
extracting it.

## Verify and extract on another machine

```bash
bash environments/gluonts-p7d-verify.sh \
  "/path/to/<P7C_RUN_ID>.zip" \
  "/path/to/<P7C_RUN_ID>-verified"
```

The destination must be absent or empty. Verification occurs before final placement. The destination
contains the original archive members plus:

```text
p7d_verification_report.json
P7D_VERIFY_SHA256SUMS
```

## Safety rules

- Keep the ZIP outside the immutable source run directory.
- Do not edit the ZIP or extracted `run/` tree.
- Transfer the `.zip.sha256` sidecar with the ZIP when possible.
- P7D rejects duplicate members, absolute paths, `..`, backslashes, symlinks, encrypted members,
  unsupported compression, unsafe expansion ratios, stale inventories, and nested hash mismatch.
- Packaging does not make a blocked or failed model available and does not change `p8_eligible`.
