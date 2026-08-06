# Trusted Evidence Data Contract

## Schema version

All contracts use `schema_version=1.0.0` and strict Pydantic v2 configuration:

```python
ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)
```

Unknown fields and implicit Python-type coercion are rejected.

## Status inventory

```text
NOT_PROVIDED
OPERATOR_ASSERTED
LOCALLY_TIMESTAMPED
EXTERNALLY_TIMESTAMPED_UNVERIFIED
EXTERNALLY_TIMESTAMPED_VERIFIED
SIGNATURE_UNVERIFIED
SIGNATURE_VERIFIED
OFFICIAL_SOURCE_UNVERIFIED
OFFICIAL_SOURCE_VERIFIED
CORRECTED
REVOKED
```

Status is evidence semantics, not a generic PASS flag.

## VerificationMaterial

Each retained verifier input records:

- stable material ID;
- safe package-relative POSIX path;
- SHA-256;
- exact byte size;
- media type;
- role.

A canonical `verification_material_sha256` binds the sorted inventory. Symlinks, traversal,
absolute paths, backslashes, drive syntax, duplicate paths, and case-insensitive collisions are
rejected.

## TrustedTimeEvidence

Records:

- subject SHA-256;
- claimed UTC time;
- local record time;
- authority class and name;
- verifier ID;
- retained verification material and inventory hash.

`LOCALLY_TIMESTAMPED` requires `LOCAL_SYSTEM` authority and cannot specify an external verifier.
Only a successfully invoked external verifier can make an externally verified claim effective.

## SignatureEvidence

Records:

- signed subject SHA-256;
- signature kind and algorithm;
- signature-bytes SHA-256;
- signer and key identity;
- public-verifiability class;
- verifier and retained material.

HMAC must use `SHARED_SECRET_ONLY`. It cannot use `SIGNATURE_VERIFIED` because possession of a
shared secret is not independently public verification.

## ParserEvidence

Records:

- parser name and version;
- parser-code SHA-256;
- source format;
- raw input SHA-256;
- normalized output SHA-256;
- local parse time.

Parser evidence proves deterministic identity only when the parser bytes and all input/output
hashes are available. It does not authenticate the source.

## SourceRevisionEvidence

Supports ETag, Last-Modified, publication ID, content version, Git commit, and other explicit
revision identifiers. The revision string is preserved and separately hashed. Verified official
revision status requires retained material and a verifier ID.

## ActualSourceEvidence

Records:

- source name and exact HTTP or HTTPS URL;
- raw response-byte SHA-256 and size;
- canonical response-header SHA-256;
- fetch time;
- separately recorded publication time;
- normalized Actual payload SHA-256;
- parser evidence;
- source revision evidence;
- optional publication-time and signature evidence;
- verifier ID and retained material;
- correction-chain head when corrected or revoked.

Publication time and fetch time are distinct fields. When both are present, publication time may
not be after fetch time. This is a consistency rule, not external proof of either clock.

## CorrectionEvidence

Each correction includes:

- one-based sequence number;
- immutable subject evidence SHA-256;
- previous correction record SHA-256;
- replacement evidence SHA-256 for `CORRECTED`;
- no replacement for `REVOKED`;
- reason, actor, and timezone-aware record time;
- canonical record SHA-256.

The chain is valid only when sequences are contiguous, timestamps are non-decreasing, IDs and
record hashes are unique, subject identity is unchanged, previous hashes match, and revocation is
terminal.

## ThirdPartyEvidenceBundle

The envelope binds:

- existing prediction-lock file SHA-256;
- existing verification-seal file SHA-256;
- optional existing Actual-lock file SHA-256;
- trusted-time records;
- signature records;
- optional Actual-source record;
- append-only corrections;
- canonical bundle SHA-256.

The envelope is additive. It does not require a schema migration of existing lock or seal files.

## OfflineVerificationReport

The report separates:

- structural and material integrity;
- external claim verification;
- correction-chain verification;
- per-evidence claimed and effective status;
- third-party-verifiability;
- terminal status: `VERIFIED`, `UNVERIFIED`, `FAILED`, or `REVOKED`.
