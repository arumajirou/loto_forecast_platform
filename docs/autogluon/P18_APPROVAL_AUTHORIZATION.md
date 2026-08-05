# P18 Manual Approval and One-Time Registry Authorization

## Purpose

P18 consumes only a verified P17 decision of `ELIGIBLE_FOR_HUMAN_APPROVAL`.
It converts two independent human approvals into a short-lived authorization for
one exact future registry transaction.

P18 does not write to a registry, change a production alias, deploy a model, or
start retraining. The most permissive P18 state is:

```text
AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION
human_approval_granted=true
registry_write_authorized=true
registry_write_executed=false
promotion_status=APPROVED_NOT_REGISTERED
automatic_promotion=false
automatic_retraining=false
```

A later isolated phase must implement the registry compare-and-swap transaction.

## Required P17 state

The source directory must contain a complete and valid P17 artifact with:

```text
status=PASS
decision=ELIGIBLE_FOR_HUMAN_APPROVAL
reason_code=ALL_RULES_PASS
human_approval_required=true
human_approval_granted=false
registry_write_allowed=false
promotion_status=NOT_PROMOTED
```

P18 independently verifies the P17 `SHA256SUMS`, manifest, response, decision
self-hash, source file set, and source-tree SHA-256. A P17 result of
`NOT_ELIGIBLE` cannot be converted into an approval intent.

## Frozen registry subject

Before anyone signs, P18 freezes:

- exact registry target;
- immutable model ID;
- hexadecimal model revision;
- P17 selected candidate ID;
- model artifact SHA-256;
- data snapshot SHA-256;
- runtime environment SHA-256;
- code SHA-256;
- configuration SHA-256;
- P17 bundle and decision SHA-256;
- allowed signers file SHA-256;
- allowed signer identities;
- approval request and expiry timestamps;
- one-time 256-bit authorization nonce.

Mutable target names such as `latest`, `champion`, and `production` are rejected.
The selected candidate in the registry subject must exactly match P17.

## Approval policy

Exactly two approvals are required:

1. `model_owner`;
2. `independent_reviewer`.

The approver IDs, signer identities, and public keys must be distinct. Each
approval must acknowledge all of the following:

- `REAL_PROSPECTIVE_ACCURACY_REVIEWED`;
- `ALL_BASELINE_COMPARISONS_REVIEWED`;
- `LEAKAGE_AND_EVIDENCE_INTEGRITY_REVIEWED`;
- `ROLLBACK_AND_REGISTRY_PLAN_REVIEWED`.

The default authorization lifetime is one hour. An expired intent requires a
new intent, new nonce, and new signatures.

## Allowed signers file

P18 deliberately accepts a restricted OpenSSH allowed-signers form. It requires
exactly two non-comment lines, one principal per line, and two different
`ssh-ed25519` public keys.

```text
owner@example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
reviewer@example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
```

OpenSSH options, multiple comma-separated principals, RSA keys, duplicate
principals, and duplicate public keys are rejected. Private keys must remain
outside the repository and outside all P18 artifacts.

## Prepare the registry subject

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

cp \
  configs/autogluon_campaign/p18_registry_subject.example.json \
  /absolute/path/to/autogluon-registry-subject.json

${EDITOR:-nano} /absolute/path/to/autogluon-registry-subject.json
```

Every placeholder SHA-256 and the candidate ID must be replaced with reviewed
immutable values.

## Create the approval intent

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

RUN_ID="autogluon-p18-$(date -u +%Y%m%dT%H%M%SZ)"
CEREMONY="artifacts/autogluon-p18-ceremony/${RUN_ID}"
mkdir -p "${CEREMONY}"

PYTHONPATH=src uv run python \
  scripts/run_autogluon_p18_approval.py intent \
  --p17 /absolute/path/to/p17-evidence \
  --subject /absolute/path/to/autogluon-registry-subject.json \
  --policy configs/autogluon_campaign/p18_approval_policy.json \
  --allowed-signers /absolute/path/to/allowed_signers \
  --run-id "${RUN_ID}" \
  --git-commit "$(git rev-parse HEAD)" \
  --output "${CEREMONY}/APPROVAL_INTENT.json"
```

The CLI generates a random 256-bit nonce when `--authorization-nonce` is not
provided. The expiry defaults to the policy lifetime.

## Prepare and sign the model-owner approval

```bash
PYTHONPATH=src uv run python \
  scripts/run_autogluon_p18_approval.py prepare-approval \
  --intent "${CEREMONY}/APPROVAL_INTENT.json" \
  --role model_owner \
  --approver-id owner@example \
  --signer-identity owner@example \
  --rationale \
    "Reviewed real prospective accuracy, baselines, integrity, and rollback." \
  --output-dir "${CEREMONY}/model-owner"

ssh-keygen -Y sign \
  -f /absolute/path/to/model-owner-ed25519-private-key \
  -n loto-autogluon-p18 \
  "${CEREMONY}/model-owner/approval-signing-payload.bin"

PYTHONPATH=src uv run python \
  scripts/run_autogluon_p18_approval.py finalize-approval \
  --draft "${CEREMONY}/model-owner/approval-draft.json" \
  --signature \
    "${CEREMONY}/model-owner/approval-signing-payload.bin.sig" \
  --output "${CEREMONY}/model-owner/approval.json"
```

## Prepare and sign the independent-reviewer approval

Use a different person, identity, and private key.

```bash
PYTHONPATH=src uv run python \
  scripts/run_autogluon_p18_approval.py prepare-approval \
  --intent "${CEREMONY}/APPROVAL_INTENT.json" \
  --role independent_reviewer \
  --approver-id reviewer@example \
  --signer-identity reviewer@example \
  --rationale \
    "Independently reviewed prospective evidence and registry rollback." \
  --output-dir "${CEREMONY}/independent-reviewer"

ssh-keygen -Y sign \
  -f /absolute/path/to/reviewer-ed25519-private-key \
  -n loto-autogluon-p18 \
  "${CEREMONY}/independent-reviewer/approval-signing-payload.bin"

PYTHONPATH=src uv run python \
  scripts/run_autogluon_p18_approval.py finalize-approval \
  --draft "${CEREMONY}/independent-reviewer/approval-draft.json" \
  --signature \
    "${CEREMONY}/independent-reviewer/approval-signing-payload.bin.sig" \
  --output "${CEREMONY}/independent-reviewer/approval.json"
```

## Issue the one-time authorization

```bash
OUTPUT="artifacts/autogluon-p18/${RUN_ID}"

PYTHONPATH=src uv run python \
  scripts/run_autogluon_p18_approval.py authorize \
  --p17 /absolute/path/to/p17-evidence \
  --intent "${CEREMONY}/APPROVAL_INTENT.json" \
  --approval "${CEREMONY}/model-owner/approval.json" \
  --approval "${CEREMONY}/independent-reviewer/approval.json" \
  --allowed-signers /absolute/path/to/allowed_signers \
  --output "${OUTPUT}"
```

The output directory must be absent or empty. P18 copies the public allowed
signers file into the evidence bundle and independently re-verifies both
signatures before publication.

## Verify the authorization

```bash
PYTHONPATH=src uv run python \
  scripts/run_autogluon_p18_approval.py verify \
  --run "${OUTPUT}"
```

Verification repeats:

- complete SHA-256 coverage;
- manifest coverage and sizes;
- intent self-hash;
- allowed signer inventory and hash;
- both OpenSSH signatures;
- P17 lineage;
- authorization seal;
- exact future registry subject;
- response and transaction-requirement semantics.

## Durable evidence

```text
REQUEST_METADATA.json
P17_LINEAGE.json
APPROVAL_INTENT.json
APPROVALS.json
ALLOWED_SIGNERS
SIGNATURE_VERIFICATION.json
REGISTRY_AUTHORIZATION.json
REGISTRY_TRANSACTION_REQUIREMENTS.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

## One-time transaction boundary

The future registry transaction must provide:

- the exact authorization ID and seal;
- the exact immutable subject;
- an unexpired and unconsumed authorization;
- the expected current registry-state SHA-256;
- a compare-and-swap write;
- append-only authorization and nonce consumption records.

P18 records these requirements but performs no write. A later transaction phase
must atomically change `consumed=false` to a committed consumption record.

## Certification boundary

The authoring tests use synthetic P17 evidence and an injected signature
verifier. They test contracts, artifact integrity, signer inventory, state
transitions, CLI routing, and tamper rejection. They do not certify:

- real AutoGluon 1.5.0 runtime execution;
- real P16 or P17 evidence;
- a completed two-person OpenSSH ceremony;
- private-key storage or operator identity;
- soundness of the human review;
- target registry availability or compare-and-swap behavior;
- a registry mutation, model registration, deployment, or rollback;
- Ruff, mypy, full repository pytest, GitHub Actions, or GPU evidence.
