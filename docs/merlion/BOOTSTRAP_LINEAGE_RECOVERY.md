# Merlion bootstrap lineage recovery

## Target-host incident

The first network-capable target-host Run reached lock resolution with:

- CPython `3.11.14`;
- uv `0.11.32`;
- `salesforce-merlion==2.0.4`;
- NumPy `1.26.4`;
- 43 resolved packages;
- 227 registry artifacts with SHA-256 hashes.

The generated lock used:

```text
requires-python = "==3.11.*"
```

The isolated project used:

```text
requires-python = ">=3.11,<3.12"
```

These constraints describe the same Python 3.11 minor line. The original string comparison
incorrectly classified them as different.

The resumable runner also created `PREFLIGHT.json`, bound its self-hash into
`BOOTSTRAP_PLAN.json`, and then invoked the inner bootstrap. The inner bootstrap regenerated the
same path with a new timestamp. Evidence packaging correctly rejected the resulting lineage
mismatch, but no evidence ZIP could be produced.

The rejected lock was preserved externally by SHA-256 and removed from the worktree without
commitment.

## Corrective behavior

### Semantic Python-constraint audit

The audit now evaluates supported PEP 440 comparison clauses rather than comparing text.

Equivalent examples:

```text
==3.11.*
>=3.11,<3.12
>=3.11.0,<3.12.0
```

Broader or narrower ranges remain blocked. Unsupported clauses fail closed.

### Immutable preflight reuse

The resumable runner now:

1. creates `PREFLIGHT.json` once;
2. creates `BOOTSTRAP_PLAN.json` from that exact report;
3. validates both self-hashes and their lineage;
4. records the preflight file SHA-256;
5. invokes the inner bootstrap with `MERLION_PREFLIGHT_MODE=REUSE`;
6. requires the expected preflight report SHA-256;
7. verifies that the preflight file bytes did not change.

Standalone bootstrap retains `GENERATE` mode.

### Evidence-packaging failure separation

A blocked bootstrap is still eligible for a verified `BOOTSTRAP_BLOCKED` evidence ZIP. If the
packager itself fails, the runner does not overwrite the original bootstrap failure. It writes:

```text
EVIDENCE_PACKAGING_FAILURE.json
```

The record contains both the original bootstrap exit code and the packaging exit code. The runner
uses exit code `70` for this distinct failure class.

## Retry boundary

A retry must use:

- the corrected exact branch head;
- a clean worktree;
- a new immutable Run ID;
- no reuse or commitment of the rejected lock;
- a verified evidence ZIP before license review or lock admission.

No Holdout or Prospective data is opened during bootstrap recovery.
