# Trusted Time and Actual Source Evidence Architecture

## Status

`FOUNDATION_ONLY / OFFLINE_SCHEMA_VERIFIED / EXTERNAL_VERIFIERS_NOT_IMPLEMENTED`

## Purpose

This package adds an external evidence envelope around existing prediction-lock, actual-lock,
and verification-seal artifacts. It does not rewrite those artifacts and does not treat a local
clock, a local hash, or an operator assertion as independent third-party proof.

## Repository findings

The implementation was designed after reviewing these existing boundaries:

- `main` provides `INTEGRITY.json`, a self-digest and complete file inventory. It detects
  modified, missing, and untracked files, but it is not a digital signature or trusted timestamp.
- PR #53 adds `VERIFICATION_SEAL.json`, which binds immutable run content to a local seal time.
  Its own boundary explicitly excludes digital signing and external timestamping.
- PR #60 makes verified lineage trees portable and independently rechecks relocation, hashes,
  seals, and safe ZIP paths. It explicitly does not provide a digital signature or external
  trusted timestamp.
- PR #63 adds `PREDICTION_LOCK.json` with `timestamp_authority=LOCAL_SYSTEM_UTC`. The lock binds
  prediction bytes but does not prove that the local system clock was correct.
- PR #64 adds `ACTUALS_LOCK.json`. It separates optional asserted publication time from ingestion
  time and records `actual_publication_time_verified=false`.

The foundation therefore sits beside those schemas instead of modifying them.

## Package layout

```text
src/loto/trusted_evidence/
  __init__.py
  statuses.py
  canonical.py
  model_base.py
  time_evidence.py
  signature_evidence.py
  parser_evidence.py
  source_revision.py
  actual_source.py
  correction_evidence.py
  bundle.py
  verification_results.py
  contracts.py
  interfaces.py
  material_verifier.py
  verifier_common.py
  evidence_decisions.py
  corrections.py
  legacy.py
  offline_verifier.py
```

## Trust layers

### Integrity

SHA-256 binds exact bytes, canonical objects, verification-material inventories, correction
records, and the complete evidence bundle. Integrity does not prove who produced the bytes or
when they existed.

### Assertion

`OPERATOR_ASSERTED` and `LOCALLY_TIMESTAMPED` preserve useful operator evidence without
presenting it as independent proof.

### External verification

An external status becomes effective only after an injected offline verifier validates retained
material. The foundation contains verifier protocols but no RFC 3161, Sigstore, public-key,
transparency-log, or official-source implementation.

### Correction history

Corrections are append-only records. Each record hashes its complete payload and links to the
previous record hash. A revoked record must terminate the chain.

## Fail-closed rules

- Local system time remains `LOCALLY_TIMESTAMPED`.
- An unavailable timestamp verifier downgrades a claimed verified timestamp to
  `EXTERNALLY_TIMESTAMPED_UNVERIFIED`.
- HMAC is classified as `SHARED_SECRET_ONLY` and cannot be represented as a public verified
  signature.
- An unavailable public-signature verifier produces `SIGNATURE_UNVERIFIED`.
- An unavailable official-source verifier produces `OFFICIAL_SOURCE_UNVERIFIED`.
- Material hash, size, path, or correction-chain failure makes offline verification `FAILED`.
- A terminal revocation makes the bundle `REVOKED`.

## External verifier boundary

`VerifierRegistry` accepts three protocol implementations:

```text
TrustedTimeVerifier
SignatureVerifier
ActualSourceVerifier
```

Each verifier receives already-parsed strict evidence and a local material root. It must return a
hash-bound `ExternalVerificationResult`. The offline verifier checks verifier identity, domain,
subject SHA-256, verification-material SHA-256, and effective status.

No verifier is auto-discovered. No network access is performed.

## Backward compatibility

`legacy.py` maps existing fields without upgrading their meaning:

- `timestamp_authority=LOCAL_SYSTEM_UTC` becomes `LOCALLY_TIMESTAMPED`;
- a legacy Actual source label becomes `OPERATOR_ASSERTED`;
- an absent timestamp or Actual lock becomes `NOT_PROVIDED` or `None`;
- existing prediction-lock, actual-lock, and verification-seal bytes remain unchanged.

Integration into PR #60, #63, or #64 is intentionally deferred to a separate PR after their stack
is resolved.
