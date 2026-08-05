# P11 Signed Primary-Promotion Authorization

## Purpose

P11 consumes an integrity-verified P10 result of
`ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW`, the current deployment-state snapshot,
and three independent SSH-signed approvals. It issues one short-lived
authorization for one exact future P12 primary-promotion transaction.

P11 does not modify the deployment state. It does not replace the primary,
clear the canary, publish predictions, retrain, roll back, or alter a public
endpoint.

A successful P11 result is:

```text
AUTHORIZED_FOR_ONE_PRIMARY_PROMOTION_TRANSACTION
promotion_status=APPROVED_NOT_PRIMARY
primary_promotion_authorized=true
primary_promotion_executed=false
primary_binding_changed=false
canary_binding_changed=false
prediction_publication_allowed=false
automatic_primary_promotion=false
automatic_retraining=false
automatic_rollback=false
```

## Required P10 state

P11 accepts only an integrity-verified P10 bundle containing:

```text
decision=ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW
primary_promotion_eligible=true
primary_promotion_executed=false
primary_binding_changed=false
prediction_publication_allowed=false
```

The P10 `SHA256SUMS` must cover the complete bundle. P11 freezes the P10 bundle,
formal decision, aggregated metrics, baseline comparison, and window evidence
hashes.

## Deployment precondition

The current deployment state is validated before the intent is created. The
P10 subject and activation ID must exactly match the active shadow canary.

The signed intent fixes:

- deployment target;
- deployment-state generation and SHA-256;
- exact primary binding before the transaction;
- exact shadow-canary binding before the transaction;
- exact target primary binding;
- `clear_canary_on_commit=true`;
- rollback target;
- P10 metrics and evidence hashes;
- monitoring thresholds;
- authorization nonce, issue time, and expiry.

Any state change after signing makes the later P12 compare-and-swap fail.

## Three-person approval policy

P11 requires exactly one approval from each role:

1. `model_owner`;
2. `independent_reviewer`;
3. `operations_owner`.

Approver IDs and SSH signer identities must all be distinct. Every signer
acknowledges:

- `P10_METRICS_AND_BASELINES_REVIEWED`;
- `REAL_PROSPECTIVE_CHRONOLOGY_REVIEWED`;
- `RUNTIME_AND_ARTIFACT_IDENTITY_REVIEWED`;
- `PRIMARY_IMPACT_AND_ROLLBACK_REVIEWED`;
- `MONITORING_AND_ABORT_THRESHOLDS_REVIEWED`.

The SSH namespace is `loto-sktime-p11`. The default authorization lifetime is
30 minutes. Expiry requires a new deployment snapshot, intent, and signatures.

## Prepare the ceremony

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export SKTIME_P11_P10_EVIDENCE_DIR="$(
  printf '%s' \
    '/absolute/path/to/p10/shadow-canary-evaluation'
)"
export SKTIME_P11_DEPLOYMENT_STATE="$(
  printf '%s' \
    '/mnt/e/env/deployment/sktime-deployment.json'
)"
export SKTIME_P11_ALLOWED_SIGNERS_FILE="$(
  printf '%s' \
    '/absolute/path/to/p11-allowed-signers'
)"

bash scripts/prepare_sktime_p11_ceremony.sh
```

The command emits:

```text
artifacts/sktime-p11-ceremony/<RUN_ID>/
├── ceremony.env
└── intent/
    ├── request-base.json
    ├── PRIMARY_PROMOTION_INTENT.json
    └── PRIMARY_PROMOTION_INTENT_SHA256
```

## Prepare and sign approvals

Run the following once for each role with a different person and private key.

```bash
source /absolute/path/to/ceremony.env

INTENT="${SKTIME_P11_CEREMONY_DIR}/intent/PRIMARY_PROMOTION_INTENT.json"
ROLE="model_owner"
APPROVER_ID="owner-person"
SIGNER_IDENTITY="owner@example"
APPROVAL_DIR="${SKTIME_P11_CEREMONY_DIR}/${ROLE}"

PYTHONPATH=src uv run python \
  scripts/prepare_sktime_p11_approval.py \
  --intent "${INTENT}" \
  --role "${ROLE}" \
  --approver-id "${APPROVER_ID}" \
  --signer-identity "${SIGNER_IDENTITY}" \
  --approved-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --rationale "Reviewed metrics, chronology, runtime, impact, and rollback." \
  --output-dir "${APPROVAL_DIR}"

ssh-keygen -Y sign \
  -f /absolute/path/to/private-key \
  -n loto-sktime-p11 \
  "${APPROVAL_DIR}/approval-signing-payload.bin"

PYTHONPATH=src uv run python \
  scripts/finalize_sktime_p11_approval.py \
  --draft "${APPROVAL_DIR}/approval-draft.json" \
  --signature "${APPROVAL_DIR}/approval-signing-payload.bin.sig" \
  --output "${APPROVAL_DIR}/approval.json"
```

Repeat for `independent_reviewer` and `operations_owner`.

## Run formal certification

```bash
source /absolute/path/to/ceremony.env

export SKTIME_P11_APPROVAL_FILES="$(
  printf '%s:%s:%s' \
    "${SKTIME_P11_CEREMONY_DIR}/model_owner/approval.json" \
    "${SKTIME_P11_CEREMONY_DIR}/independent_reviewer/approval.json" \
    "${SKTIME_P11_CEREMONY_DIR}/operations_owner/approval.json"
)"

bash scripts/start_sktime_p11_certification_tmux.sh
tmux attach -t sktime-p11-primary-promotion-authorization
```

## Durable evidence

A successful run creates:

```text
REQUEST_METADATA.json
P10_LINEAGE.json
DEPLOYMENT_PRECONDITION.json
PRIMARY_PROMOTION_INTENT.json
APPROVALS.json
SIGNATURE_VERIFICATION.json
PRIMARY_PROMOTION_AUTHORIZATION.json
P12_TRANSACTION_REQUIREMENTS.json
ROLLBACK_AND_MONITORING_PLAN.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

## P12 boundary

P12 must reject the transaction when:

- the authorization seal differs;
- the authorization is expired or consumed;
- the transaction nonce was consumed;
- the deployment-state SHA changed;
- the primary binding changed;
- the canary binding changed;
- the target primary differs;
- canary clearing differs;
- authorization consumption and binding updates are not one atomic commit.

P11 only issues the authorization. It does not execute P12.

## Certification boundary

Authoring tests verify the contract, signatures interface, exact bindings,
one-time transaction guard, artifact integrity, and tamper rejection. They do
not prove that real P10 evidence is eligible, the human judgment is correct,
private keys are protected, the deployment state is current, or P12 succeeded.
