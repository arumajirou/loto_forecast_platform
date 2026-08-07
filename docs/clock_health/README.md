# Clock Health Gate v1

Status: `PARTIALLY_VERIFIED / FOUNDATION_ONLY / FIXTURE_TESTS_PASS`.

This package evaluates whether a host clock is operationally healthy enough to satisfy a
Prediction Lock precondition. It does not create trusted third-party time, a public signature,
an RFC 3161 timestamp, or Sigstore evidence.

## Boundaries

The pure evaluator accepts a normalized `ClockObservation` and a hashed `ClockHealthPolicy`.
It does not execute subprocesses, read project data, open Holdout, inspect Prospective actuals,
or modify an existing Prediction Lock. The optional chronyc adapter is outside the pure core and
uses only fixed argv with `shell=False` and a bounded timeout.

Only `HEALTHY` produces `prediction_lock_allowed=true`. `DEGRADED`, `BLOCKED`, and `UNKNOWN`
all fail closed for Prediction Lock.

## Commands

Offline retained-text check:

```bash
PYTHONPATH=src python scripts/run_clock_health_check.py \
  --mode files \
  --policy configs/clock_health/default_policy.json \
  --tracking-file /absolute/path/chronyc-tracking.txt \
  --sources-file /absolute/path/chronyc-sources.txt \
  --observed-at-utc 2026-08-06T09:00:00Z \
  --output-dir /absolute/path/clock-health-evidence
```

Target-host chronyc probe:

```bash
PYTHONPATH=src python scripts/run_clock_health_check.py \
  --mode chronyc \
  --policy configs/clock_health/default_policy.json \
  --timeout-seconds 5 \
  --output-dir /absolute/path/clock-health-evidence
```

The target-host command is provided but was not executed during this foundation implementation.

## Exit codes

- `0`: `HEALTHY`; Prediction Lock precondition allowed.
- `1`: `DEGRADED`, `BLOCKED`, or `UNKNOWN`; Prediction Lock precondition denied.
- `2`: malformed arguments, policy, files, environment, or persistence failure.

## Evidence

Each successful invocation writes raw stdout/stderr, strict observation, policy, decision,
`ARTIFACT_MANIFEST.json`, and `SHA256SUMS`. Verification rejects raw-byte drift, parser-code
drift, incomplete inventory, duplicate checksum paths, extra files, and cross-object hash mismatch.
