# Specification

## Status semantics

| Status | Meaning | Prediction Lock precondition |
|---|---|---|
| `HEALTHY` | All required checks pass | allowed |
| `DEGRADED` | No failure/unknown, at least one warning | denied |
| `BLOCKED` | At least one policy failure | denied |
| `UNKNOWN` | No failure, but required evidence is incomplete | denied |

Failure takes precedence over unknown; unknown takes precedence over warning.

## Checks

The evaluator emits one bounded `ClockCheckResult` for:

1. parser and command completeness;
2. synchronization;
3. leap status;
4. stratum;
5. absolute last offset;
6. RMS offset;
7. root delay;
8. root dispersion;
9. skew ppm;
10. online source count;
11. sample age;
12. wall/monotonic continuity.

Threshold checks have warning and block values. Missing values become `UNKNOWN`. Zero online
sources are `BLOCKED`; insufficient redundancy is `DEGRADED`.

## Continuity

```text
difference_ns = abs(wall_delta_ns - monotonic_delta_ns)
clock_step_detected = difference_ns > step_threshold_ns
```

A detected step blocks the decision. A continuity threshold that does not equal the evaluated
policy threshold is `UNKNOWN`, preventing evidence from being silently reused under another policy.

## Chronyc adapter

The only executable argv are:

```text
chronyc -n tracking
chronyc -n sources -v
```

No caller-supplied executable, argument interpolation, shell string, or environment mutation is
accepted. The adapter records command outcome rather than treating process launch as health proof.

## Trust boundary

A healthy result proves only that the retained local observations pass the selected operational
policy. The decision contract fixes these fields to false:

```text
external_trust_established
trusted_time_evidence_generated
signature_evidence_generated
```
