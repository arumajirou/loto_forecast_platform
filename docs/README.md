# Documentation

## Status

`CURRENT`

This directory contains both current repository documentation and dated historical design/verification records. Use the [Documentation Contract](DOCUMENTATION_CONTRACT.md) to determine which material may be treated as current authority.

## Current entry points

- [Documentation Contract](DOCUMENTATION_CONTRACT.md)
- [Architecture](ARCHITECTURE.md)
- [Evaluation Protocol](EVALUATION_PROTOCOL.md)
- [Data Contracts](DATA_CONTRACTS.md)
- [Model Inventory](MODEL_INVENTORY.md)
- [Windows Installation](WINDOWS_INSTALL.md)
- [Operations](OPERATIONS.md)

Changing test totals, coverage percentages, model totals, Git HEAD values, workflow results, and similar volatile status must come from generated evidence rather than hand-maintained prose.

## Historical records

Historical documents remain useful evidence of earlier design and verification states, but their values are not current repository-wide status. Examples include:

- [Implementation Status v3](IMPLEMENTATION_STATUS_V3.md)
- [Full Coverage implementation plan](../specs/001-full-coverage/plan.md)
- [Version Single-Source Verification Report](../VERIFICATION_REPORT.md)

Historical result numbers and historical merge state are preserved rather than silently rewritten.

## Component documentation

A missing standalone document whose name matches a source package is not, by itself, an implementation gap. Repository-wide component mapping must be evidence-backed; source directories are not renamed merely to make documentation names symmetrical.

A machine-readable component registry and generated component status/index will be added only after their rows can be reproduced from repository-visible evidence or imported from a fixed audit artifact without inference.

## Scope boundary

Feature-specific documentation packages retain their own detailed requirements, design, verification, runbook, and handoff material. This index defines repository-wide navigation and authority rules; it does not replace those scoped documents.
