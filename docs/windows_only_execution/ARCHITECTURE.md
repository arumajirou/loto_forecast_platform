# Architecture — Windows-only execution

## Current execution topology

```text
Operator PowerShell 7
        |
        +--> GitHub / gh exact-SHA audit
        |
        +--> local native Windows checkout
        |       |
        |       +--> uv / managed Python
        |       +--> protocol generation
        |       +--> baseline OOF
        |       +--> Timer runtime
        |
        +--> Windows self-hosted Actions runner
                runner: az-loto-windows
                install: C:\actions-runner
                service account: NT AUTHORITY\NETWORK SERVICE
```

Linux and WSL are not part of the currently executable operator topology. Historical Linux CI/evidence remains immutable archival evidence.

## Evidence layers

1. **Repository identity** — Git commit, raw-tree SHA-256, clean worktree.
2. **Data identity** — frozen development snapshot and checksums.
3. **Protocol identity** — `EvaluationProtocolV2`, comparison budget hash, protocol-set SHA-256.
4. **Runtime identity** — package versions, CPU/GPU/RAM, device and fallback state.
5. **Prediction identity** — immutable prediction record + SHA-256 seal + timestamp before actual read.
6. **Evaluation identity** — metrics, baselines, seeds, fold/target inventory.

## Portability boundary

The Windows portability CI validates dependency/package behavior but is not the formal scientific execution architecture by itself. Formal execution must add data/protocol/runtime identities and prediction sealing.

## Self-reference avoidance

Protocol-generation scripts that determine `code_hash` must not be added to the code-bearing tree immediately before hashing if doing so would change the hash they are trying to bind. Evidence-generation helpers should run outside the frozen execution tree or be included intentionally before the final hash is calculated.

## Failure isolation

- runner/service/PATH problems -> environment failure;
- workflow syntax/shell selection -> workflow failure;
- dependency resolution/package build -> portability failure;
- protocol/data hash mismatch -> evidence/data failure;
- model load/inference/shape/device -> runtime failure;
- metrics/sealing/actual-order violation -> scientific protocol failure.

These categories must not be collapsed into a generic CI failure.