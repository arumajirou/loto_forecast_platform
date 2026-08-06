# Changelog

## 1.0.0 - 2026-08-06

- Added strict Research Source Registry contracts.
- Added duplicate, revision, artifact, license, remote-code, release, mirror, supersession,
  strict-type, datetime, and non-claim controls.
- Added 11 conservatively classified initial source records.
- Added deterministic registry hashing and a validation CLI.
- Added focused tests and the complete governance documentation set.
- Hardened verified-intake completeness, repository URL identity, package-version pinning, and
  reviewed remote-code allowlist/artifact binding after substantive self-review.
- Added final fail-closed gates for paper title/identifier, repository types, exact and unique
  package identity, verified runtime compatibility, contamination evidence, official URL review
  completeness, remote required-file binding, and status-state consistency.
- Split the contract implementation and focused tests into narrow modules while preserving the
  original public import surface and all 54 passing contract tests.
