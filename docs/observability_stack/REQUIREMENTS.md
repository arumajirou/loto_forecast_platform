# LGTM Operations Stack v1 Requirements

## Functional requirements

- Provide local single-node Grafana, Alloy, Prometheus, Loki and Tempo services.
- Route application Prometheus metrics through Alloy to Prometheus.
- Route structured JSONL logs through Alloy to Loki.
- Accept OTLP gRPC/HTTP signals through Alloy and route traces to Tempo and logs to Loki.
- Provision Grafana datasources and a stable platform overview dashboard from files.
- Persist service state in named volumes with explicit retention policies.
- Provide static validation, immutable image digest resolution, startup, smoke, shutdown, backup and restore
  commands.
- Provide bounded local alert rules with runbook links. Notification delivery is outside this increment.

## Security requirements

- Bind every host listener to `127.0.0.1`.
- Do not mount the Docker socket.
- Do not enable privileged, host network or host PID modes.
- Disable Grafana anonymous access, sign-up, analytics reporting and update checks.
- Read Grafana administrator credentials from mode-0600 secret files.
- Do not commit runtime secrets, environment overrides, image digest locks, backups or runtime state.
- Treat Loki and Tempo as unauthenticated internal services; do not expose them beyond loopback.

## Reliability requirements

- Use exact reviewed tags and require runtime resolution to immutable image digests.
- Fail startup when digest locks or required secret files are missing.
- Use bounded Alloy remote-write and OTLP queues/retry windows.
- Preserve Prometheus, Loki, Tempo, Grafana and Alloy state across restart.
- Verify backup archives with SHA-256 before restore.
- Require explicit `CONFIRM_RESTORE=YES` and never auto-start after restore.

## Verification requirements

- Static validator and focused tests must pass.
- Python and shell files must compile/parse.
- YAML and JSON must parse.
- Native component validators, Compose rendering and live write/read certification must run when a container
  runtime and registry access are available.
- A successful container start alone is not formal certification.
