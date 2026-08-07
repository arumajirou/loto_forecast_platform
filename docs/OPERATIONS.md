# Operations

## Status

`CURRENT_POLICY`

This document defines repository-wide operational safety rules. Environment-specific runbooks may add concrete service/timer commands, but they must not weaken the evidence and promotion boundaries below.

## Run lifecycle

Operational workflows should use explicit Run IDs and persist enough evidence to recover configuration, data/code identity, model/revision, seed, prediction outputs, actuals, evaluation metrics, runtime/device information, logs, and artifact hashes.

A scheduler starting a job is not evidence that the job completed successfully. Completion and promotion are separate states.

## Retraining and search

New actual data may trigger a retraining or evaluation workflow, but it must not silently replace a production binding or champion.

A retraining/search cycle must preserve the active chronological protocol and create new evidence rather than overwriting prior run artifacts. Holdout or Prospective outcomes observed by an earlier generation must not be recycled as untouched tuning data for a modified generation.

Automatic scheduling does not authorize automatic promotion.

## Prediction operations

Prospective predictions are locked before actual outcomes are introduced. Prediction-lock verification is a prerequisite for treating a prospective artifact as formally fixed.

Actual ingestion/scoring occurs as a separate later operation. The lock and the subsequent actual/scoring evidence should remain independently auditable.

## Runtime operations

Model catalog availability, process startup, and runtime certification are distinct states.

Where runtime certification is required, the operator evidence should include load/inference/output/device checks and explicit CPU-fallback status. GPU-certified runs should retain process/device/VRAM evidence when the certification profile requires it.

## Failure policy

Fail closed on evidence that can invalidate a formal result, including:

- data/provenance inconsistency;
- future-information or chronological-boundary violation;
- prediction-lock or hash verification failure;
- non-finite inference output;
- missing mandatory model/revision/runtime identity;
- destructive mutation of authoritative Raw evidence;
- irreversible migration/promotion without its explicit gate.

Transient infrastructure failures may be retried only within the workflow's idempotency/retry contract. A retry is not allowed to convert an unknown or unexecuted verification result into PASS.

## Promotion and rollback

Promotion, production binding, deployment, and rollback are controlled operations with their own evidence. A candidate may be trained, evaluated, registered, or canaried without becoming the active production binding.

Rollback should point to a previously verified release/binding rather than mutating historical artifacts in place.

## Deployment adapters

The repository contains environment-specific deployment assets such as systemd units and observability configuration. Those assets are deployment adapters, not proof that Linux/systemd is the only valid repository environment.

Windows and Linux repository operations have separate portability concerns. Hardware/OS-specific runtime certification remains scoped to the environment actually verified.

## Monitoring

Operational monitoring should surface at minimum:

- run state and failure classification;
- data freshness/provenance anomalies;
- prediction-lock/scoring state;
- runtime/device evidence where applicable;
- resource failures such as OOM or unavailable accelerators;
- promotion/binding state;
- reconciliation or persistence failures.

Monitoring data is supporting evidence; it does not replace immutable run/artifact evidence.

## Current non-claims

This policy does not claim that every optional service, database, GPU provider, notification destination, backup/restore path, or deployment adapter is currently certified. Feature-specific verification reports must state what was actually executed.
