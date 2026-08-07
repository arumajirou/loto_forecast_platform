# Documentation Contract

## Status

`CURRENT`

This document defines how repository documentation is classified and which materials may be treated as current authority.

## Classification

| Class | Meaning |
|---|---|
| `CURRENT` | Current normative description of behavior, architecture, policy, or navigation. |
| `HISTORICAL` | Dated design or verification snapshot preserved without rewriting its original results. |
| `GENERATED` | Machine-generated status or evidence derived from code, registry, or execution. |
| `UPDATE_DOC` | Current-looking document known to require alignment. |
| `IMPLEMENTATION_GAP` | A gap supported by implementation/documentation evidence, not merely by a missing same-name document. |
| `NOT_APPLICABLE` | Intentionally outside the current authority model; a reason is required. |

## Current-document rules

Current prose must not manually maintain volatile values such as:

- pytest pass totals;
- coverage percentages;
- model totals;
- open PR counts;
- the current Git HEAD.

Changing status belongs in generated evidence or a machine-readable registry.

## Historical-document rules

Historical verification and design records are evidence of what was claimed or verified at that point in time.

Therefore:

- historical result numbers are not silently rewritten;
- historical merge state is not silently rewritten;
- relocation requires an index/disposition first;
- current status is added separately rather than altering the old record.

## Component authority

A component without a standalone same-name document is **not** automatically an implementation gap.

`REVIEW_REQUIRED` means that authority is unresolved. It does not mean the component is broken, missing, deprecated, or production-ready.

When a machine-readable component registry is present, only mappings with explicit evidence may be marked `CONFIRMED`. Unknown mappings remain unresolved rather than being inferred from directory-name similarity.

## Source layout

Documentation alignment does not require renaming `src/loto/**` directories merely to mirror documentation directory names.

Semantic mappings are preferred when established component boundaries and documentation vocabulary differ.

## Current front doors

- [Documentation index](README.md)
- [Architecture](ARCHITECTURE.md)

Additional component indexes and generated status documents may be added only after their source evidence is reproducible from the repository or imported from a fixed audit artifact.

## Historical examples

The following remain historical records and must not be interpreted as live repository-wide status:

- [`IMPLEMENTATION_STATUS_V3.md`](IMPLEMENTATION_STATUS_V3.md)
- [`../specs/001-full-coverage/plan.md`](../specs/001-full-coverage/plan.md)
- [`../VERIFICATION_REPORT.md`](../VERIFICATION_REPORT.md)
