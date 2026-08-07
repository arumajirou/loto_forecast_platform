# Changelog

## PR-A

- Added isolated Python 3.10 environment declaration without a fabricated lockfile.
- Added strict request/response contracts, dynamic game geometry, context geometry, and
  chronology validation.
- Added pending remote-code review, snapshot provenance, fail-closed provider skeleton,
  focused tests, and Timer-specific documentation.
- Replaced Python 3.11-only `StrEnum` use and separated observed source HEAD from the
  unpinned checkpoint source revision.
- Hardened the provider CLI so success, invalid requests, and pending runtime states return
  exit codes 0, 1, and 2 respectively, and request files cannot be overwritten.
- Recomputed calendar-axis draw-number gaps and hardened remote-code review JSON, allowlist,
  reviewer, and timezone-aware UTC validation.
- Did not modify root dependencies, shared catalogs, workers, CLI, workflows, or README.
