# LGTM Operations Stack v1 Runbook

## Component down

1. Confirm the listener remains loopback-only with `ss -ltnp`.
2. Run `docker compose ... ps` and inspect the affected container's bounded recent logs.
3. Verify disk space and volume availability.
4. Validate the exact digest lock and configuration before restart.
5. Do not delete a persistent volume as a recovery shortcut.

## Telemetry drops

1. Inspect Alloy queue and exporter metrics.
2. Check Prometheus/Loki/Tempo readiness and network reachability.
3. Determine whether the application emission rate exceeds the reviewed queue/resource budget.
4. Preserve drop counters and timestamps as evidence; do not hide the incident by resetting state.

## Artifact integrity failure

1. Stop promotion or production binding immediately.
2. Verify artifact manifest and SHA-256 from the immutable source.
3. Correlate Run ID, trace ID and registry record without adding them as metric labels.
4. Follow the artifact-integrity and prediction-lock governance runbooks.

## Prediction lock verification

1. Block scoring/promotion that depends on the failed lock.
2. Verify lock timestamp, SHA-256, code/config/data identity and trusted-time evidence.
3. Do not regenerate or overwrite the historical lock artifact.

## Pipeline no recent success

1. Confirm the stage is expected to run within 24 hours; silence only with a reviewed rule change.
2. Check scheduler, data availability and upstream dependency readiness.
3. Compare the latest immutable run/evidence record rather than relying only on telemetry.

## Backup and restore

Use `backup_restore.sh`. Restore requires checksum verification and `CONFIRM_RESTORE=YES`. After restore,
perform native validation and live smoke manually before starting dependent workloads.
