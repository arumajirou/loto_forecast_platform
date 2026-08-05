# BasicTS formal P0 verification receipt

Status: `TARGET_HOST_EXECUTION_PENDING`

This procedure creates an external, deterministic receipt for a completed BasicTS formal P0 bundle.
The receipt is not stored inside the source bundle, so it does not alter the original recursive
manifest or `SHA256SUMS` evidence.

## Purpose

The receipt closes two gaps that a standalone verification report does not close by itself:

- it requires the formal evidence Git commit to equal an explicitly expected commit;
- it anchors the complete source bundle checksum map with a canonical bundle fingerprint.

The receipt also records SHA-256 values for:

- `FORMAL_P0_STATUS.json`;
- `FORMAL_P0_MANIFEST.json`;
- the source `SHA256SUMS` file;
- the canonical independent verification report;
- the canonical complete bundle checksum map.

It does not provide cryptographic signing, an external timestamp authority, or independent
re-execution of dependency installation, training, or inference.

## Create a receipt

Run this only after the formal P0 command succeeds and the source bundle is no longer being written.

```bash
set -Eeuo pipefail

cd /mnt/e/env/ts/loto_forecast_platform || exit 1

EXPECTED_HEAD="$(git rev-parse HEAD)"
RUN_ID="<completed-formal-run-id>"
RUN_DIR="${PWD}/artifacts/basicts/formal-p0/${RUN_ID}"
RECEIPT="${PWD}/artifacts/basicts/formal-p0/${RUN_ID}.receipt.json"

PYTHONPATH="${PWD}/src" \
python -m loto.basicts_campaign.formal_receipt create \
  --run-dir "${RUN_DIR}" \
  --expected-git-commit "${EXPECTED_HEAD}" \
  --receipt "${RECEIPT}"
```

PASS requires both output lines:

```text
BASICTS_FORMAL_P0_RECEIPT=PASS
RECEIPT=<absolute receipt path>
```

The command also writes `<receipt>.sha256`. Existing receipt or checksum paths are never
overwritten. The receipt path must be outside the formal source bundle.

## Re-verify a receipt

Use the same expected commit and source bundle later to prove that neither the receipt nor the
source evidence has changed.

```bash
PYTHONPATH="${PWD}/src" \
python -m loto.basicts_campaign.formal_receipt verify \
  --run-dir "${RUN_DIR}" \
  --expected-git-commit "${EXPECTED_HEAD}" \
  --receipt "${RECEIPT}"
```

Verification performs all independent formal bundle checks again, verifies the detached receipt
checksum, rebuilds the deterministic receipt, and requires exact equality with the stored receipt.

## Promotion boundary

A PASS receipt confirms consistency between the expected Git commit, the retained formal evidence,
and the external receipt at verification time. It does not make the Draft PR merge-ready by itself.
Before promotion, still review the isolated `uv.lock`, dependency audit, BasicTS identity, import
allowlist, DLinear runtime evidence, seed, request hashes, and repository-wide tests.
