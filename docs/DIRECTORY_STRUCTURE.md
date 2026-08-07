# Directory Structure

## Status

`CURRENT`

This document describes stable repository boundaries. It intentionally avoids a hand-maintained exhaustive list of every package or file because that list changes frequently and should be generated from repository evidence when needed.

## Major areas

```text
src/loto/    Python package implementation
tests/       automated verification
docs/        current and historical documentation
specs/       dated specifications and implementation plans
configs/     declarative experiment/runtime configuration
scripts/     research, verification, audit, and operational entry points
deploy/      service, observability, and deployment assets
.github/     GitHub workflows, repository automation, and repository skills
```

## Source-package boundaries

`src/loto/**` is organized by implementation responsibility rather than documentation-directory symmetry. Examples include data, feature generation, models, evaluation, orchestration, registry, prediction sealing/locking, runtime certification, telemetry/observability, provider/framework adapters, and research campaigns.

A source directory must not be renamed solely because a documentation package uses a different vocabulary. When names differ, an evidence-backed semantic mapping is preferred.

## Documentation boundaries

Repository-wide current authority starts at [docs/README.md](README.md) and is governed by [DOCUMENTATION_CONTRACT.md](DOCUMENTATION_CONTRACT.md).

Feature-specific documentation packages may contain their own requirements, architecture, detailed design, test plan, verification report, runbook, and handoff. Dated design and verification records remain historical evidence unless explicitly promoted to current authority.

## Generated inventories

Exhaustive file trees, component inventories, test counts, model counts, and current commit identifiers are volatile. They should be generated from a fixed repository snapshot and accompanied by hashes rather than manually copied into this document.
