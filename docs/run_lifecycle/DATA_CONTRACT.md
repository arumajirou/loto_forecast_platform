# Data Contract

## Contract inventory

Required public contracts:

- `RunPhase`
- `RunStatus`
- `RunCommandType`
- `RunCommand`
- `RunEvent`
- `RunLease`
- `RunAggregate`
- `IdempotencyRecord`
- `TransitionRule`
- `TransitionDecision`
- `EvidenceReference`
- `LifecycleValidationFinding`
- `LifecycleValidationReport`
- `LifecycleSnapshot`

Supporting immutable contracts include `CanonicalJsonObject`, `HashBinding`, `DecisionEvidence`,
`DuplicateCommandEvidence`, `EffectResult`, and `CommandExecutionResult`.

## Canonical payload representation

Semantic parameters and event/result payloads use `CanonicalJsonObject.text`. The text must parse to
one JSON object and must already equal the canonical representation. This avoids mutable nested
Python mappings inside frozen evidence models while retaining machine-readable JSON.

## Identifier policy

Identifiers match:

```regex
^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$
```

Path separators, whitespace, traversal components and shell metacharacters are rejected.

## SHA-256 policy

SHA values are exactly 64 lowercase hexadecimal characters. Hashes prove byte/semantic identity;
they do not prove trusted time, official source, signer identity, runtime success or accuracy.

## Datetime policy

Every evidence datetime must be timezone-aware and have UTC offset zero. Naive datetimes and
non-UTC offsets fail validation.

## Event-chain invariants

- sequence begins at 1;
- sequence and revision are equal;
- expected revision is `revision - 1`;
- Run ID is constant;
- prior hash matches the previous event;
- event hash recalculates exactly;
- transition target matches the matrix;
- timestamps do not move backwards;
- sealed output name cannot bind to another hash.
