# Data Contract

## ResearchSourceRecord

Required fields include source and logical model IDs, source kind, paper identity, paper publication
state, official repositories, revisions, artifacts, compatibility, license boundary, remote-code
policy, contamination declaration, release status, source verification report, supersession, and
non-claims.

## ArtifactIdentity

- `path`: safe POSIX relative path;
- `required`: strict boolean;
- `size_bytes`: non-negative strict integer or explicit unresolved state;
- `sha256`: lowercase SHA-256 or explicit unresolved state.

## LicenseBoundary

Code and weight licenses are separate mandatory fields with separate source evidence. Equal license
values are allowed when independently supported; collapsing them into one field is not allowed.

## RuntimeCompatibilityDeclaration

Python, Torch, Transformers, and package identities are declarations only. `VERIFIED` means the
compatibility evidence was reviewed, not that the package was installed or executed by this PR.

## RemoteCodePolicy

`trust_remote_code=true` requires a concrete review policy ID and an explicit review status. It does
not itself authorize execution. Allowed remote files remain empty while review is pending. A
`VERIFIED` review requires a non-empty, duplicate-free, safe relative-path allowlist, and every
allowed file must exist in the artifact inventory with exact size and SHA-256.

## ContaminationDeclaration

The record stores pretraining disclosure, benchmark contamination risk, benchmark names, and
verification state. `UNKNOWN` is valid and preferable to inference from marketing text.

## SourceVerificationReport

The report contains a timezone-aware check time, intake status, method, official URLs, findings, and
blockers. A naive datetime is invalid.

## ResearchSourceRegistry

The registry uses schema version `1.0.0`, a timezone-aware generation timestamp, and an ordered set
of records. Record order affects the canonical registry digest and must be changed intentionally.
Registry storage uses `registry.v1.json` as a strict index and `records/*.json` as one immutable source record per file. The loader validates containment and composes the records before applying the Registry contract.

## Verified intake gate

`VERIFIED_FOR_INTAKE` rejects unresolved paper identity, unknown release state, sentinel or
noncanonical repositories, unresolved revisions, license sources, commercial eligibility, retained
blockers, missing required artifacts, and unresolved required artifact size or SHA-256. A completed
remote-code review may reach this state only after its allowlisted files are pinned in the artifact
inventory.
