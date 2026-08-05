# P7 Manual Approval and Registry Authorization

## Purpose

P7 converts a verified P6 result of `ELIGIBLE_FOR_HUMAN_APPROVAL` into a
short-lived, one-time authorization for one exact future registry transaction.

P7 does not write to MLflow, PostgreSQL, a model registry, or any production
alias. It only issues an immutable authorization artifact after two independent
SSH signatures pass verification.

A successful P7 result is:

```text
AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION
promotion_status=APPROVED_NOT_REGISTERED
registry_write_authorized=true
registry_write_executed=false
automatic_promotion=false
automatic_retraining=false
```

The registry write belongs to a later P8 compare-and-swap transaction.

## Required P6 state

P7 refuses all P6 bundles except an integrity-verified bundle containing:

```text
decision=ELIGIBLE_FOR_HUMAN_APPROVAL
eligible_for_human_approval=true
human_approval_required=true
human_approval_granted=false
registry_write_allowed=false
promotion_status=NOT_PROMOTED
```

The P6 `SHA256SUMS`, `PROMOTION_DECISION.json`, and `response.json` are checked
again before P7 request construction.

## Exact registry subject

The approval intent fixes all of the following before anyone signs:

- registry target;
- immutable model ID and revision;
- P6 shadow candidate ID;
- model artifact SHA-256;
- data snapshot SHA-256;
- runtime environment SHA-256;
- code SHA-256;
- P6 bundle and decision SHA-256;
- allowed signers file SHA-256;
- approval request time and expiry;
- one-time 256-bit authorization nonce.

No field may be changed after signing. A later registry transaction must match
the complete subject exactly.

## Approval policy

The formal policy requires exactly two approvals:

1. `model_owner`;
2. `independent_reviewer`.

The approver IDs and SSH signer identities must be distinct. Each approval must
acknowledge all four risks:

- `REAL_PROSPECTIVE_ACCURACY_REVIEWED`;
- `BASELINE_COMPARISON_REVIEWED`;
- `LEAKAGE_AND_INTEGRITY_REVIEWED`;
- `ROLLBACK_PLAN_REVIEWED`.

The default authorization lifetime is one hour. The authorization is one-time
use and is not renewable. Expiry requires a new intent and new signatures.

## Allowed signers file

Use the OpenSSH allowed signers format. Each principal must have a different
key.

```text
owner@example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
reviewer@example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
```

Private keys must remain outside the repository and outside P7 artifacts.

## Prepare the registry subject

Copy the example and replace every placeholder with reviewed immutable values.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

cp \
  configs/sktime_campaign/registry_subject.example.json \
  /absolute/path/to/registry-subject.json

${EDITOR:-nano} /absolute/path/to/registry-subject.json
```

The `model_revision` must be an immutable 7-to-64-character hexadecimal
revision. Mutable names such as `latest`, `main`, or `champion` are not valid.

## Prepare the approval ceremony

The P6 directory must be the verified `manual-promotion-gate` evidence
directory, not only its parent run directory.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export SKTIME_P7_P6_EVIDENCE_DIR="/absolute/path/to/p6/manual-promotion-gate"
export SKTIME_P7_SUBJECT_CONFIG="/absolute/path/to/registry-subject.json"
export SKTIME_P7_ALLOWED_SIGNERS_FILE="/absolute/path/to/allowed_signers"

bash scripts/prepare_sktime_p7_ceremony.sh
```

This creates:

```text
artifacts/sktime-p7-ceremony/<RUN_ID>/
├── CODE_SHA256_INPUT
├── CONFIG_SHA256_INPUT
├── ceremony.env
└── intent/
    ├── APPROVAL_INTENT.json
    └── APPROVAL_INTENT_SHA256
```

The generated `ceremony.env` preserves the exact run ID, timestamps, nonce,
subject paths, and policy needed by the later formal runner.

## Prepare and sign the model-owner approval

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

CEREMONY_DIR="/absolute/path/to/artifacts/sktime-p7-ceremony/<RUN_ID>"
INTENT="${CEREMONY_DIR}/intent/APPROVAL_INTENT.json"
OWNER_DIR="${CEREMONY_DIR}/model-owner"

uv run \
  --project environments/sktime-classic-py312 \
  --group dev \
  python scripts/prepare_sktime_p7_approval.py \
  --intent "${INTENT}" \
  --role model_owner \
  --approver-id owner@example \
  --signer-identity owner@example \
  --approved-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --rationale "Reviewed real prospective metrics, integrity, and rollback." \
  --output-dir "${OWNER_DIR}"

ssh-keygen -Y sign \
  -f /absolute/path/to/model-owner-ed25519-key \
  -n loto-sktime-p7 \
  "${OWNER_DIR}/approval-signing-payload.bin"

uv run \
  --project environments/sktime-classic-py312 \
  --group dev \
  python scripts/finalize_sktime_p7_approval.py \
  --draft "${OWNER_DIR}/approval-draft.json" \
  --signature "${OWNER_DIR}/approval-signing-payload.bin.sig" \
  --output "${OWNER_DIR}/approval.json"
```

## Prepare and sign the independent-reviewer approval

Use a different person, signer identity, and private key.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

CEREMONY_DIR="/absolute/path/to/artifacts/sktime-p7-ceremony/<RUN_ID>"
INTENT="${CEREMONY_DIR}/intent/APPROVAL_INTENT.json"
REVIEWER_DIR="${CEREMONY_DIR}/independent-reviewer"

uv run \
  --project environments/sktime-classic-py312 \
  --group dev \
  python scripts/prepare_sktime_p7_approval.py \
  --intent "${INTENT}" \
  --role independent_reviewer \
  --approver-id reviewer@example \
  --signer-identity reviewer@example \
  --approved-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --rationale "Independently reviewed metrics, leakage checks, and rollback." \
  --output-dir "${REVIEWER_DIR}"

ssh-keygen -Y sign \
  -f /absolute/path/to/reviewer-ed25519-key \
  -n loto-sktime-p7 \
  "${REVIEWER_DIR}/approval-signing-payload.bin"

uv run \
  --project environments/sktime-classic-py312 \
  --group dev \
  python scripts/finalize_sktime_p7_approval.py \
  --draft "${REVIEWER_DIR}/approval-draft.json" \
  --signature "${REVIEWER_DIR}/approval-signing-payload.bin.sig" \
  --output "${REVIEWER_DIR}/approval.json"
```

## Run formal P7 certification

Complete the ceremony and run P7 before the one-hour expiry.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

CEREMONY_DIR="/absolute/path/to/artifacts/sktime-p7-ceremony/<RUN_ID>"
source "${CEREMONY_DIR}/ceremony.env"

export SKTIME_P7_APPROVAL_FILES="$(
  printf '%s:%s' \
    "${CEREMONY_DIR}/model-owner/approval.json" \
    "${CEREMONY_DIR}/independent-reviewer/approval.json"
)"

bash scripts/start_sktime_p7_certification_tmux.sh
```

Attach to the protected terminal:

```bash
tmux attach -t sktime-p7-approval-authorization
```

## Durable evidence

A successful run creates:

```text
REQUEST_METADATA.json
P6_LINEAGE.json
APPROVAL_INTENT.json
APPROVALS.json
SIGNATURE_VERIFICATION.json
REGISTRY_AUTHORIZATION.json
REGISTRY_TRANSACTION_REQUIREMENTS.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

Verify the latest run:

```bash
ROOT="/mnt/e/env/ts/loto_forecast_platform"

RUN_DIR="$(
  find "${ROOT}/artifacts/sktime-p7" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -printf '%T@ %p\n' \
  | sort -nr \
  | head -n 1 \
  | cut -d' ' -f2-
)"

EVIDENCE_DIR="${RUN_DIR}/manual-approval-authorization"

cat "${RUN_DIR}/exit_code.txt"
cat "${EVIDENCE_DIR}/response.json"
cat "${EVIDENCE_DIR}/REGISTRY_AUTHORIZATION.json"

(
  cd "${EVIDENCE_DIR}" || exit 1
  sha256sum -c SHA256SUMS
)
```

## One-time transaction guard

P7 also defines the contract used by P8. A transaction is rejected when:

- the authorization seal differs;
- the authorization is expired;
- the authorization ID was already consumed;
- the transaction nonce was already consumed;
- any registry-subject field differs;
- the expected current registry state hash differs;
- the write is not compare-and-swap;
- the consumption ledger is not append-only.

P7 validates the transaction request but does not execute it. The returned P7
state remains `APPROVED_NOT_REGISTERED`.

## Certification boundary

The authoring harness verifies the contract and tamper controls. It does not
prove that real P6 evidence is eligible, that the human reviewers made a sound
judgment, that private keys are properly protected, that the target registry is
available, or that a P8 registry transaction succeeded.
