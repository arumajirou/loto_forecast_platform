# Specification

## State model

The allowed intake statuses are:

- `VERIFIED_FOR_INTAKE`;
- `CONDITIONAL`;
- `REMOTE_CODE_REVIEW_REQUIRED`;
- `LICENSE_REVIEW_REQUIRED`;
- `CHECKPOINT_REVIEW_REQUIRED`;
- `NOT_RELEASED`;
- `BLOCKED`.

`VERIFIED_FOR_INTAKE` is a source-intake state only. It requires an available release, concrete
paper title/identifier/date/URL, type-correct canonical repositories, pinned source/model revisions,
verified runtime compatibility with exact package identities, resolved contamination evidence,
resolved license evidence and commercial eligibility, complete official-URL review evidence, no
unresolved blockers, and pinned size/SHA-256 for every required model artifact. It still does not
claim artifact download, dependency resolution, load, inference, evaluation, or production
registration.

## Revision rules

A formal revision is one lowercase 40-character commit SHA. The explicit sentinels are accepted as
unresolved evidence states. Release tags may be recorded in findings, but must be resolved to a
commit before formal verification.

## SHA-256 rules

A verified digest is exactly 64 lowercase hexadecimal characters. Uppercase, prefixes, whitespace,
shortened hashes, Git blob IDs, ETags, Xet IDs, and copied approximate checksums are rejected as
SHA-256 evidence.

## Repository identity

Each repository identity declares whether it is official, canonical, and a mirror. A canonical
repository must be official and non-mirror. Mirrors can be retained only as non-canonical evidence.

## Status gates

- remote code without reviewed bytes: `REMOTE_CODE_REVIEW_REQUIRED` or stronger blocking state;
- reviewed remote code: non-empty safe allowlist, required-artifact membership, exact size, and
  SHA-256;
- unknown code or weight license: `LICENSE_REVIEW_REQUIRED`, `CONDITIONAL`, or `BLOCKED`;
- released repository with unverified checkpoint bytes: `CHECKPOINT_REVIEW_REQUIRED`;
- no released required checkpoint: `NOT_RELEASED` or `BLOCKED`;
- unresolved runtime compatibility or package identity: a non-verified intake status;
- unresolved pretraining disclosure or contamination risk: a non-verified intake status;
- incomplete official URL verification evidence: a non-verified intake status;
- retrieval methods with unresolved leakage controls: `CONDITIONAL` or `BLOCKED`.

## Canonical identity

The registry digest is SHA-256 over deterministic JSON with sorted keys, compact separators,
UTF-8, finite values only, and the complete validated registry payload.
Registry storage uses `registry.v1.json` as a strict index and `records/*.json` as one immutable source record per file. The loader validates containment and composes the records before applying the Registry contract.
