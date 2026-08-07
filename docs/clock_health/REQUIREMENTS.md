# Requirements

## Functional

- CH-001: Accept injected normalized observations in the core evaluator.
- CH-002: Preserve synchronization, leap, stratum, offset, RMS, delay, dispersion, skew, source
  count, sample age, and continuity evidence.
- CH-003: Return exactly `HEALTHY`, `DEGRADED`, `BLOCKED`, or `UNKNOWN`.
- CH-004: Set `prediction_lock_allowed=true` only for `HEALTHY`.
- CH-005: Never represent local clock health as external trusted time or signature verification.
- CH-006: Bind raw chronyc bytes, parser identity, parser source SHA-256, command argv, timeout,
  exit code, stdout/stderr hashes, and byte sizes.
- CH-007: Detect a wall-clock versus monotonic-clock step over the policy threshold.
- CH-008: Persist complete, strict, independently re-verifiable evidence.

## Non-functional

- Pydantic v2 contracts use `extra="forbid"`, strict types, frozen models, validated defaults,
  finite numbers, lowercase SHA-256, and timezone-aware UTC timestamps.
- Canonical JSON uses UTF-8, sorted keys, compact separators, and explicit list order.
- JSON readers reject duplicate keys and non-finite constants.
- The core evaluator imports no subprocess module.
- The chronyc adapter uses fixed argv, `shell=False`, timeout, and sanitized structured evidence.
- No root dependency, lockfile, workflow, API, Prediction Lock, Trusted Evidence, data, Registry,
  Promotion, Holdout, or Prospective path changes are permitted.
