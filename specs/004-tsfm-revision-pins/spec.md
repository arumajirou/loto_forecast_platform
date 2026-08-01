# TSFM Revision Pin Manifest

## Status
IMPLEMENTED / LOCALLY_VERIFIED

## Requirement
The platform shall accept only explicit full commit identifiers for repository-backed TSFM models. It shall reject branches, tags, abbreviated hashes, unknown model IDs, repository mismatches and duplicate entries. Applying a manifest shall return new immutable catalog entries and shall not mutate the base catalog.

## Non-goals
The feature does not query Hugging Face or GitHub and does not invent revisions. Network resolution remains an explicit reviewed operation.
