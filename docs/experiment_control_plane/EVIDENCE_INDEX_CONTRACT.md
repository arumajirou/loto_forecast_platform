# Evidence Index Contract

## Purpose

The evidence index makes experiment evidence discoverable and independently verifiable without copying large or secret-bearing artifacts into GitHub.

## Evidence roles

```text
plan
configuration
data_snapshot
protocol
data_access_ledger
runtime_certification
training_log
metrics
trace
model_artifact
prediction
prediction_lock
actual_source
actual_lock
evaluation
baseline_comparison
multi_seed_summary
resource_usage
cost_report
result_summary
downstream_commit_receipt
promotion_handoff
```

Role ownership remains with the domain that creates the evidence.

## Index fields

Each entry contains:

- stable evidence ID and role;
- exact subject identities (Run, plan, protocol and relevant model/data IDs);
- content-addressed URI without credentials;
- SHA-256 and byte size;
- media type and optional schema/version;
- producer component/code identity;
- creation time and trusted-time reference if required;
- confidentiality/retention classification;
- optional signature/attestation reference;
- verification receipts.

## Verification levels

```text
DECLARED
LOCATOR_REACHABLE
HASH_VERIFIED
SIGNATURE_VERIFIED
CONTRACT_VERIFIED
SUBJECT_BOUND
REJECTED
UNAVAILABLE
```

These are evidence verification levels, not run lifecycle states. A higher level requires all lower relevant checks and an immutable verification receipt.

## Content-addressing

Recommended object key:

```text
sha256/<first-two-hex>/<full-sha256>
```

A metadata alias may point to the content key, but aliases are not identity. Existing bytes under a digest key must be re-read or provider-checksummed before reuse.

## Security

Rejected URI forms include:

```text
https://user:password@host/...
https://host/path?token=...
s3://ACCESS_KEY:SECRET@bucket/...
file paths outside configured roots
relative paths that escape a Run workspace
```

Evidence reports use secret masking and never embed environment dumps without allowlisting.

## Retention and deletion

- Retention class is explicit per entry.
- Deletion requires an approved retention action and produces a tombstone receipt.
- The index retains digest, prior locator and deletion reason even when bytes expire.
- GitHub Actions artifacts may be indexed as temporary transport evidence but cannot satisfy permanent evidence retention alone.

## Result acceptance gate

A result cannot be accepted when any required role is missing, unavailable, digest-mismatched, subject-mismatched, produced by an untrusted revision, or below the verification level required by policy.
