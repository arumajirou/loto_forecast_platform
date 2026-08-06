# Data Contract

## ClockObservation

Required identity and measurements:

```text
schema_version
observation_id
observed_at_utc
synchronized
leap_status
stratum
last_offset_seconds
rms_offset_seconds
root_delay_seconds
root_dispersion_seconds
skew_ppm
online_source_count
sample_age_seconds
sources[]
continuity
parser_evidence
observation_sha256
```

Offsets and delays use SI seconds. `last_offset_seconds` retains its sign; policy evaluation uses
its absolute magnitude. Source names are not retained; only their SHA-256 identities are stored.
At most one source may be selected, source identities must be unique, and the online count must
match the source inventory.

## ClockParserEvidence

The parser evidence binds parser ID/version, exact parser source bytes, raw tracking/source bytes,
byte sizes, bounded parse error codes, and optional command evidence. Command evidence retains fixed
argv, duration, timeout, exit code, and stdout/stderr hash and size, not raw exceptions.

## ClockHealthPolicy

Every policy contains warning/block thresholds and a canonical `policy_sha256`. Any threshold,
required-state, leap-state, source-count, or continuity-threshold change changes the policy hash.

## ClockHealthDecision

The decision binds the observation and policy hashes, all check outcomes, failed/warning/unknown
inventories, continuity result, evaluation UTC time, Prediction Lock precondition, explicit trust
non-claims, and a canonical `decision_sha256`.

## Persistence

The evidence directory contains seven primary files, a manifest, and `SHA256SUMS`. The verifier
requires exact inventory equality; missing, extra, renamed, duplicated, size-drifted, or hash-drifted
entries fail closed.
