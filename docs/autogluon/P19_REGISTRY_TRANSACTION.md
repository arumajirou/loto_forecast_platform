# P19 one-time atomic registry compare-and-swap transaction

## Purpose

P19 consumes one integrity-verified P18 authorization and performs one exact state transition in the
local `file-json-cas-v1` reference registry. It is the first AutoGluon phase that may change a
registry file, but the permitted target is only the explicitly reviewed local JSON file bound into
the P18 signatures.

P19 does not connect to MLflow, PostgreSQL, a remote registry service, a public endpoint, or a
production alias. It does not deploy, serve, retrain, or automatically roll back a model.

A newly committed transition reports:

```text
REGISTRY_TRANSACTION_COMMITTED
registry_write_executed=true
external_registry_write_executed=false
promotion_status=REGISTERED_NOT_DEPLOYED
deployment_status=NOT_DEPLOYED
automatic_deployment=false
automatic_retraining=false
```

An exact retry reports:

```text
IDEMPOTENT_ALREADY_COMMITTED
registry_write_executed=false
```

## Required P18 state

P19 re-verifies the complete P18 evidence directory, including its SHA-256 inventory, manifest,
authorization seal, approval intent, two approvals, allowed-signers inventory, and signatures. It
accepts only:

```text
decision=AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION
registry_write_authorized=true
registry_write_executed=false
one_time_use=true
consumed=false
promotion_status=APPROVED_NOT_REGISTERED
```

For a new state transition, the execution time must be inside the P18 authorization window. An exact
retry of a transaction that already committed is read-only and may still return its prior result
after the original authorization expires.

## Reference registry state

The registry is one regular JSON file with this logical state:

```text
schema_version=autogluon-file-json-registry-v1
backend=file-json-cas-v1
registry_target=<exact P18 file+json URI>
generation=<history length>
current_binding=<immutable P18 subject or null>
consumed_authorization_ids=<append-only ordered ledger>
consumed_transaction_nonces=<append-only ordered ledger>
history=<append-only sealed transaction records>
deployment_status=NOT_DEPLOYED
automatic_deployment=false
automatic_retraining=false
state_sha256=<canonical self-hash>
```

Every history record has its own canonical SHA-256 seal. Registry verification reconstructs every
prefix state and requires each record's `expected_pre_state_sha256` to equal the previous
generation.
Rehashing a changed record and outer state therefore does not make a broken history chain valid.

## Compare-and-swap and atomicity

The transaction requires the exact current `state_sha256`. Processing occurs under an OS file lock.
For a new commit, P19:

1. verifies P18 and fingerprints it;
2. verifies the registry target and raw filesystem path;
3. locks the registry;
4. reloads and verifies the current state;
5. rejects a stale expected state;
6. checks authorization-ID and nonce ledgers;
7. creates one sealed history record;
8. appends the authorization ID, nonce, and record in one next state;
9. writes a same-directory temporary file;
10. flushes and `fsync`s the file;
11. atomically replaces the registry file;
12. `fsync`s the parent directory;
13. reloads and verifies the post-state;
14. verifies that the P18 source remained unchanged;
15. publishes a separate immutable evidence directory.

If evidence publication fails after a registry commit, an exact retry with a fresh empty evidence
directory recreates evidence without a second registry mutation.

## Replay behavior

The transaction identity binds:

- P19 schema;
- run ID;
- Git commit;
- fixed P19 policy;
- P18 authorization ID and seal;
- transaction nonce;
- expected pre-state SHA-256;
- complete immutable registry subject.

The same authorization ID and nonce with the same transaction identity is an idempotent retry. A
changed Git commit, nonce, subject, expected state, authorization seal, or policy is a conflicting
replay and fails closed. Reusing only an authorization ID or only a transaction nonce also fails.

## Filesystem safety

P19 rejects:

- non-`file+json` targets;
- relative targets, query strings, fragments, hosts, or parent traversal;
- a registry path that differs from the signed P18 target;
- symbolic links in the registry path or any existing parent component;
- non-regular registry files;
- invalid registry or history seals;
- a non-empty evidence output directory;
- an evidence output inside the P18 source;
- symlinks, special files, missing files, extra files, or SHA drift in evidence.

## Durable evidence

```text
REQUEST_METADATA.json
P18_LINEAGE.json
TRANSACTION_PLAN.json
PRE_REGISTRY_STATE.json
TRANSACTION_RECEIPT.json
POST_REGISTRY_STATE.json
AUTHORIZATION_CONSUMPTION.json
ROLLBACK_PLAN.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

`P18_LINEAGE.json` retains the full sealed authorization and transaction requirements plus the P18
source-tree and file hashes. The independent P19 verifier recomputes the transaction identity,
registry-state seals, history membership, append-only ledgers, generation transition, receipt,
consumption record, rollback boundary, response, manifest, and SHA coverage.

## Rollback boundary

P19 records the previous and registered bindings, but never executes rollback. A rollback requires:

- fresh reviewed eligibility evidence;
- a fresh two-person P18 authorization;
- a fresh P19 transaction nonce;
- compare-and-swap against the current post-state.

The committed model remains `REGISTERED_NOT_DEPLOYED`.

## Operator workflow

Choose the local reference registry path before preparing and signing the P18 subject. The exact
`file+json` URI in P18 must resolve to the same path.

Bootstrap an absent registry exactly once:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

REGISTRY_PATH="${PWD}/artifacts/autogluon/p19-reference-registry/state.json"
mkdir -p "$(dirname "${REGISTRY_PATH}")"
REGISTRY_TARGET="file+json://${REGISTRY_PATH}"

PYTHONPATH=src uv run python scripts/run_autogluon_p19_registry.py bootstrap \
  --registry "${REGISTRY_PATH}" \
  --registry-target "${REGISTRY_TARGET}"
```

Read and review the current state:

```bash
PYTHONPATH=src uv run python scripts/run_autogluon_p19_registry.py state \
  --registry "${REGISTRY_PATH}"
```

After a real P18 authorization exists for that exact target, capture the current state SHA-256 and
execute P19 before authorization expiry:

```bash
P18_DIR="/absolute/path/to/p18-evidence"
EXPECTED_STATE_SHA256="$(
  python - "${REGISTRY_PATH}" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text())["state_sha256"])
PY
)"
RUN_ID="autogluon-p19-$(date -u +%Y%m%dT%H%M%SZ)"
TRANSACTION_NONCE="$(openssl rand -hex 32)"
OUTPUT="${PWD}/artifacts/autogluon/p19-registry-transactions/${RUN_ID}"

PYTHONPATH=src uv run python scripts/run_autogluon_p19_registry.py transact \
  --p18 "${P18_DIR}" \
  --registry "${REGISTRY_PATH}" \
  --output "${OUTPUT}" \
  --run-id "${RUN_ID}" \
  --git-commit "$(git rev-parse HEAD)" \
  --expected-state-sha256 "${EXPECTED_STATE_SHA256}" \
  --transaction-nonce "${TRANSACTION_NONCE}" \
  --executed-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --policy configs/autogluon_campaign/p19_registry_policy.json
```

Verify the resulting evidence independently:

```bash
PYTHONPATH=src uv run python scripts/run_autogluon_p19_registry.py verify \
  --run "${OUTPUT}"

(
  cd "${OUTPUT}" || exit 1
  sha256sum -c SHA256SUMS
)
```

## Certification boundary

The authoring tests use temporary local registry files and injected P18 signature verification. They
verify the CAS contract, atomic local replacement, history-chain reconstruction, one-time ledgers,
retry behavior, concurrent exact requests, evidence integrity, and CLI routing. They do not prove:

- a real AutoGluon 1.5.0 runtime result;
- real P16/P17 evidence or real prospective accuracy;
- a real two-person OpenSSH P18 ceremony;
- a reviewed target-host registry transaction;
- MLflow, PostgreSQL, remote registry, alias, serving, or deployment changes;
- rollback execution;
- Ruff, mypy, full repository pytest, GitHub Actions, or GPU evidence.
