# Common Promotion Subject and Status Taxonomy Architecture

## Status

`FOUNDATION_ONLY / NO_PRODUCTION_MUTATION / PROVIDER_MIGRATION_PENDING`

This package defines a provider-neutral identity and lifecycle vocabulary. It does not perform a
promotion, generate a human approval, write a registry, activate a canary, or replace a primary
binding.

## Repository findings

The current platform uses several meanings of “promotion”:

1. main `evaluation/promotion.py` produces an accuracy-oriented recommendation;
2. NeuralForecast promotion gates authorize later evaluation stages after runtime/API evidence;
3. provider-specific P6 gates produce human-review eligibility;
4. P7 approval ceremonies authorize one registry transaction;
5. P8 commits registry state but deliberately does not deploy;
6. P9 activates a shadow canary without changing primary;
7. P10 produces primary-review eligibility from sealed prospective evidence;
8. P11 authorizes one primary transaction but deliberately does not execute it.

Those meanings are related but not interchangeable. The foundation therefore separates the
immutable subject from its mutable lifecycle.

## Core objects

### PromotionSubject

`PromotionSubject` binds the exact candidate and all evidence that determines what is under review:

- candidate, provider, repository and immutable model revision;
- model artifact, runtime environment, code, configuration and data snapshot hashes;
- protocol hash;
- OOF, Holdout and Prospective evidence;
- baseline comparison;
- prediction-lock evidence;
- runtime-certification evidence;
- license eligibility.

The subject fixes `first_place_only_selection=false`, `best_seed_only_selection=false`, and
`automatic_retraining=false`. Canonical JSON excludes only `subject_sha256`. Any bound value change
creates a different subject hash.

### Lifecycle status

Status is not stored inside the subject. A transition references the subject hash and independent
runtime, accuracy, approval, registry and deployment axes. This avoids silently changing the object
that humans approved when operational state changes.

### Separate axes

- Runtime: `UNVERIFIED`, `VERIFIED`, `FAILED`.
- Accuracy: `NOT_EVALUATED`, `PENDING`, `VERIFIED_ELIGIBLE`, `VERIFIED_INELIGIBLE`.
- Registry: `NOT_REGISTERED`, `AUTHORIZED`, `REGISTERED`.
- Deployment: `NOT_DEPLOYED`, `SHADOW_CANARY`, `PRIMARY`.

Runtime success cannot satisfy an accuracy requirement. Accuracy rank cannot satisfy runtime,
approval, registry, or deployment requirements.

## Status path

```text
CANDIDATE
  -> RUNTIME_UNVERIFIED
  -> RUNTIME_VERIFIED
  -> EVALUATION_PENDING
  -> SHADOW_ELIGIBLE
  -> HUMAN_REVIEW_REQUIRED
  -> APPROVED_NOT_REGISTERED
  -> REGISTERED_NOT_DEPLOYED
  -> SHADOW_CANARY_ACTIVE
  -> PRIMARY_REVIEW_ELIGIBLE
  -> PRIMARY_AUTHORIZED_NOT_EXECUTED
  -> PRIMARY_ACTIVE
```

`BLOCKED`, `REJECTED`, and `REVOKED` are terminal for one lifecycle attempt. Resuming after a block
must create a new audited attempt rather than rewriting the blocked record.

## Safety properties

- Verified runtime evidence must be real, not synthetic or injected.
- Verified OOF evidence retains multiple seeds and rejects best-seed-only selection.
- A first-place ranking is retained as evidence but never performs a transition by itself.
- Human approval evidence must already exist, sign the exact subject hash, and state its scope.
- Registry authorization, registry commit, deployment and primary activation remain separate.
- Shadow activation must not alter the primary binding.
- Primary authorization must not execute the primary binding.
- Transition validation is pure and reports that no mutation or approval generation occurred.

## Integration boundary

The package imports no provider-specific P6-P12 module. Existing provider contracts remain
authoritative until one provider at a time proves compatibility and real evidence parity. Existing
production bindings and registry state are not read or changed by this foundation.
