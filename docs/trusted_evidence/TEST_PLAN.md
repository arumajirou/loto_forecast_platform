# Trusted Evidence Test Plan

## Scope

The focused suite requires no network, model, GPU, official website, TSA, Sigstore service, or
external cryptography package.

## Schema tests

- every required status is present;
- unknown fields are rejected;
- strict Python types are enforced;
- unsafe verification-material paths are rejected;
- material inventory hashes are exact;
- all timestamps require timezone information;
- source revision values are hash-bound;
- publication and fetch times remain distinct.

## Trust-boundary tests

- local system time remains `LOCALLY_TIMESTAMPED` and not third-party verified;
- claimed external timestamp without an implementation becomes unverified;
- injected verifier success requires exact verifier, domain, subject, and material identities;
- HMAC cannot be a public verified signature;
- public signature without an implementation becomes unverified;
- official source without an implementation becomes unverified;
- injected official-source verifier can produce verified status from retained local material.

## Integrity tests

- verification-material mutation fails;
- canonical headers hash is stable across header order and name case;
- bundle mutation invalidates its canonical hash;
- correction records reject content mutation through record SHA-256;
- correction chains reject reorder, sequence gaps, changed subjects, and broken previous hashes;
- terminal revocation produces `REVOKED`.

## Compatibility tests

- legacy `LOCAL_SYSTEM_UTC` maps to `LOCALLY_TIMESTAMPED`;
- legacy Actual source label maps to `OPERATOR_ASSERTED`;
- no legacy field is upgraded to external verification;
- source lock and seal bytes are not modified.

## Static tests

The foundation source is scanned for direct HTTP, socket, TSA, Sigstore, or external verifier
imports. Provider or model imports are not permitted.

## Deferred tests

The following belong to future implementation PRs:

- RFC 3161 token parsing and certificate-chain validation;
- Sigstore or transparency-log inclusion verification;
- public-key signature verification;
- official-source domain, certificate, and publication validation;
- live HTTP retrieval and redirect policy;
- portable bundle integration with PR #60;
- prediction-lock integration with PR #63;
- Actual scoring integration with PR #64.
