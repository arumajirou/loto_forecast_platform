# P8 atomic registry transaction

P8 consumes one verified P7 authorization and performs one exact
compare-and-swap update against the `file-json-cas-v1` reference registry.
It does not deploy the registered model and does not retrain anything.

## State transition

The registry is one sealed JSON document. One atomic replacement updates all
of the following together:

- the current model binding;
- the monotonically increasing generation;
- the consumed authorization ID;
- the consumed transaction nonce;
- the append-only transaction history.

A writer must present the exact current `state_sha256`. A stale writer fails
without modifying the registry. An OS file lock serializes concurrent writers.
The replacement file is flushed, atomically renamed, and re-read before PASS.

## Safety properties

- P7 `SHA256SUMS` must verify before the request is built.
- P7 must report `AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION`.
- Candidate, revision, artifact hashes, registry target, authorization ID,
  authorization seal, and transaction nonce are immutable.
- The authorization must still be inside its validity window at commit time.
- A consumed authorization or nonce cannot create another transition.
- An exact replay returns `IDEMPOTENT_ALREADY_COMMITTED` without rewriting.
- A changed replay is rejected.
- Registry symlinks and invalid state seals are rejected.
- Automatic deployment, retraining, and rollback remain disabled.

## Bootstrap an empty reference registry

Bootstrapping creates generation zero and does not register a model.
It refuses to overwrite an existing path.

```bash
export REGISTRY_STATE="/absolute/path/to/sktime-registry.json"
export REGISTRY_TARGET="file+json://${REGISTRY_STATE}"

PYTHONPATH=src uv run python scripts/bootstrap_sktime_p8_registry.py \
  --registry-state "${REGISTRY_STATE}" \
  --registry-target "${REGISTRY_TARGET}"
```

The `registry_target` used during the earlier P7 ceremony must be the same
`file+json:///absolute/path` value.

## Execute P8

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export SKTIME_P8_P7_EVIDENCE_DIR="/absolute/path/to/p7/evidence"
export SKTIME_P8_REGISTRY_STATE="/absolute/path/to/sktime-registry.json"
export SKTIME_P8_REQUESTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export SKTIME_P8_TRANSACTION_NONCE="$(openssl rand -hex 32)"

bash scripts/start_sktime_p8_certification_tmux.sh
```

## Evidence

P8 writes:

- `REQUEST_METADATA.json`;
- `P7_LINEAGE.json`;
- `TRANSACTION_PLAN.json`;
- `PRE_REGISTRY_STATE.json`;
- `TRANSACTION_RECEIPT.json`;
- `POST_REGISTRY_STATE.json`;
- `AUTHORIZATION_CONSUMPTION.json`;
- `ROLLBACK_PLAN.json`;
- `response.json`;
- `ARTIFACT_MANIFEST.json`;
- `SHA256SUMS`.

A successful new write reports:

```text
REGISTRY_TRANSACTION_COMMITTED
promotion_status=REGISTERED_NOT_DEPLOYED
deployment_status=NOT_DEPLOYED
```

An exact retry reports `IDEMPOTENT_ALREADY_COMMITTED` and does not mutate the
registry again.

## Rollback

The transaction receipt retains both the prior and new bindings. P8 only
creates a rollback plan. A rollback requires a new P6/P7 review and a fresh P8
compare-and-swap transaction against the current post-state SHA. No automatic
rollback is performed.

## External registries

This increment intentionally certifies the transactional safety boundary on a
single-file reference backend. MLflow or PostgreSQL adapters must preserve the
same authorization, CAS, append-only consumption, idempotence, and evidence
contracts in a separately reviewed change. P8 does not claim an MLflow write,
production alias change, or deployment.
