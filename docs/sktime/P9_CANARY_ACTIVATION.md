# P9 Shadow Canary Activation

## Purpose

P9 consumes a verified P8 registration and a matching runtime probe. It places
that immutable model subject into a shadow-only canary slot. It does not change
the current primary binding, publish predictions, deploy a public endpoint,
promote the canary, retrain, or roll back automatically.

A successful transition reports:

```text
SHADOW_CANARY_ACTIVATED
promotion_status=CANARY_ACTIVE_NOT_PRIMARY
primary_binding_unchanged=true
prediction_publication_allowed=false
automatic_primary_promotion=false
automatic_retraining=false
automatic_rollback=false
```

## Runtime evidence

The probe must match the P8 subject for model ID, immutable revision, model
artifact SHA-256, runtime environment SHA-256, and code SHA-256. Formal PASS
also requires successful load, input validation, inference, finite output,
expected output shape, save/load re-prediction equality, process ID, and device
evidence. CUDA execution requires GPU PID and VRAM evidence. CPU fallback is
blocked by the default policy.

## Atomic deployment state

The reference backend is `file-json-deployment-cas-v1`. One atomic state file
contains the primary binding, canary binding, generation, consumed activation
IDs and nonces, and append-only history. The update uses an OS file lock,
expected pre-state SHA-256, `fsync`, atomic rename, and post-write verification.

An exact retry is idempotent. A stale state, changed replay, active different
canary, invalid seal, symlink, or subject mismatch fails without mutation.

## Bootstrap once

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export DEPLOYMENT_STATE="/mnt/e/env/deployment/sktime-deployment.json"
export DEPLOYMENT_TARGET="file+json://${DEPLOYMENT_STATE}"

mkdir -p "$(dirname "${DEPLOYMENT_STATE}")"
PYTHONPATH=src uv run python \
  scripts/bootstrap_sktime_p9_deployment.py \
  --deployment-state "${DEPLOYMENT_STATE}" \
  --deployment-target "${DEPLOYMENT_TARGET}"
```

## Execute after P8

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export SKTIME_P9_P8_EVIDENCE_DIR="/absolute/path/to/p8/file-registry-cas"
export SKTIME_P9_RUNTIME_PROBE="/absolute/path/to/runtime-probe.json"
export SKTIME_P9_DEPLOYMENT_STATE="/mnt/e/env/deployment/sktime-deployment.json"
export SKTIME_P9_DEPLOYMENT_TARGET="file+json://${SKTIME_P9_DEPLOYMENT_STATE}"
export SKTIME_P9_REQUESTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export SKTIME_P9_ACTIVATION_NONCE="$(openssl rand -hex 32)"

bash scripts/start_sktime_p9_certification_tmux.sh
```

## Durable evidence

- `REQUEST_METADATA.json`
- `P8_LINEAGE.json`
- `RUNTIME_PROBE.json`
- `ACTIVATION_PLAN.json`
- `PRE_DEPLOYMENT_STATE.json`
- `ACTIVATION_RECEIPT.json`
- `POST_DEPLOYMENT_STATE.json`
- `ROLLBACK_PLAN.json`
- `response.json`
- `ARTIFACT_MANIFEST.json`
- `SHA256SUMS`

The next stage is P10: collect at least the configured number of shadow draws,
score Hit@±1 and the secondary metrics, compare every baseline, and decide
whether the canary remains shadow-only, is rejected, or becomes eligible for a
separate primary-promotion review.
