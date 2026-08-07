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

Python, Torch, Transformers, and package identities are declarations only. Package names are
normalized for duplicate detection and package versions must be one exact version rather than a
floating label, range, URL, or VCS reference. `VERIFIED` requires resolved declarations and package
identity evidence; it means the compatibility evidence was reviewed, not that the package was
installed or executed by this PR.

## RemoteCodePolicy

`trust_remote_code=true` requires a concrete review policy ID and an explicit review status. It does
not itself authorize execution. Allowed remote files remain empty while review is pending. A
`VERIFIED` review requires a non-empty, duplicate-free, safe relative-path allowlist, and every
allowed file must be a required artifact with exact size and SHA-256. A non-remote policy cannot
retain an execution allowlist.

## ContaminationDeclaration

The record stores pretraining disclosure, benchmark contamination risk, benchmark names, and
verification state. `UNKNOWN` is valid and preferable to inference from marketing text. `VERIFIED`
contamination evidence requires a concrete disclosure and a resolved non-`UNKNOWN` risk.

## SourceVerificationReport

The report contains a timezone-aware check time, intake status, method, official URLs, findings, and
blockers. Duplicate URLs and duplicate, empty, or untrimmed evidence notes are invalid. A naive
datetime is invalid. Verified intake requires evidence that the canonical paper, source, model,
license, and package-source URLs were checked.

## ResearchSourceRegistry

The registry uses schema version `1.0.0`, a timezone-aware generation timestamp, and an ordered set
of records. Record order affects the canonical registry digest and must be changed intentionally.
Registry storage uses `registry.v1.json` as a strict index and `records/*.json` as one immutable source record per file. The loader validates containment and composes the records before applying the Registry contract.

## Verified intake gate

`VERIFIED_FOR_INTAKE` rejects unresolved paper title/identifier/date/URL, unknown release state,
sentinel, noncanonical, or type-inconsistent repositories, unresolved revisions, runtime
compatibility, duplicate or unresolved package identity, contamination evidence, license sources,
commercial eligibility, incomplete official-URL evidence, retained blockers, missing required
artifacts, and unresolved required artifact size or SHA-256. A completed remote-code review may reach
this state only after every allowlisted file is a required, pinned artifact.
