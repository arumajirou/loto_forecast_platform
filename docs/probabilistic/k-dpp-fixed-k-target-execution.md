# k-DPP fixed-k target-host execution control plane

## Status

`PARTIALLY_VERIFIED / CONTROL_PLANE_IMPLEMENTED / REAL_HISTORY_PENDING / CPU_FORMAL_PENDING`

This increment joins two independently reviewed worktrees without merging their branches:

- the read-only five-game export and approval worktree from the PR #104/#106 line;
- the k-DPP materialization and CPU certification worktree from the PR #119/#117 line.

The control plane creates an external workspace, freezes both Git identities and principal source
hashes, generates exact command arrays, and records three immutable evidence transitions. It does
not connect to PostgreSQL, approve data, execute a model, or claim CPU_FORMAL by itself.

## Why two worktrees remain separate

The raw-history exporter and the k-DPP runtime are in independent Draft PR stacks. Combining their
source branches merely to execute a target-host campaign would create a large synthetic integration
branch and weaken provenance. The operator instead supplies two clean checkouts:

1. an exporter checkout with the exact PR #106 head;
2. a k-DPP checkout with the exact head containing this control plane.

The workspace must be outside both repositories. Every later operation rechecks both HEAD values,
branch names, complete worktree cleanliness, Python executables, and required source-file hashes.

## Prepared artifacts

`prepare` creates:

```text
PLAN.json
COMMANDS.json
RUNBOOK.md
CONTROL_SHA256SUMS
STATE.json
events/
```

`PLAN.json` binds:

- Run ID;
- exporter repository root, branch, HEAD, Python executable, and source hashes;
- k-DPP repository root, branch, HEAD, Python executable, and source hashes;
- game and optional Numbers3/Numbers4 position;
- prediction length 1, 2, or 5;
- seed, sample count, RBF gamma, quality pseudocount, and PSD tolerance;
- configuration SHA-256;
- `source_revision` equal to the controlled k-DPP Git HEAD;
- `holdout_opened=false`;
- `prospective_opened=false`;
- `automatic_approval=false`.

`COMMANDS.json` stores argv arrays rather than shell strings. Database credentials are not included;
the exporter reads them only from the target-host environment. Human reviewer and UTC timestamp
fields remain explicit placeholders.

## Generated operator sequence

The command plan contains the following ordered operations:

1. export five-game raw history under PostgreSQL repeatable-read/read-only isolation;
2. independently verify JSON, Parquet, manifest, and SHA-256 evidence;
3. create the raw-history pending approval record;
4. approve the raw export only after five explicit human review confirmations;
5. materialize the eight-file approved source handoff;
6. record and hash the source handoff in the control ledger;
7. materialize the selected four-file k-DPP Train-only bundle;
8. create the k-DPP pending approval record;
9. approve it only after nine explicit confirmations;
10. record and hash the approved k-DPP history bundle;
11. prepare the target-host CPU certification workspace;
12. execute two separate runtime processes;
13. run the independent formal verifier;
14. record CPU_FORMAL only after a second control-plane validation.

Every generated Python invocation sets `PYTHONDONTWRITEBYTECODE=1` and an explicit checkout-specific
`PYTHONPATH`, preventing bytecode files from making either source worktree dirty.

## Immutable event ledger

The event order is fixed:

```text
SOURCE_HANDOFF_RECORDED
KDPP_HISTORY_RECORDED
CPU_FORMAL_RECORDED
```

Each event stores:

- one-based event index;
- previous event SHA-256;
- UTC recording time;
- absolute artifact locations;
- artifact tree/file SHA-256 values;
- independently derived summary fields;
- canonical event SHA-256.

Before a new event is accepted, the controller reopens every prior artifact, recomputes its hashes,
and verifies the complete event chain. Missing, reordered, renamed, extra, symlinked, or modified
event entries fail closed. `STATE.json` is a convenience pointer only; it must agree with the
immutable event sequence.

## Source handoff validation

`record-source` reuses the PR #119 source validator. It requires exactly:

```text
numbers3.json
numbers4.json
miniloto.json
loto6.json
loto7.json
history_verification.json
history_approval.json
HISTORY_HANDOFF.json
```

The controller verifies reviewer identity, UTC timestamps, source export identity, query and
database-snapshot bindings, retained JSON and Parquet hashes, five-game coverage, and no source
modification or future-actual usage.

## k-DPP history validation

`record-history` reuses the PR #117 history-bundle validator. It requires the immutable four-file
bundle plus a separate approved record. The game and optional position must equal the prepared
control plan. All fixed-cardinality, chronology, item-ID, Train-only, and approval checks are rerun.

## Independent CPU_FORMAL validation

`record-runtime` does not trust the existence of `FORMAL_VERIFICATION_REPORT.json`. It independently
reopens:

- preparation inventory and controlled certifier hash;
- copied approved history and approval;
- run inventory;
- process A and B runtime directories;
- process-pair records;
- prediction and state hashes;
- external prediction seals;
- runtime PID separation;
- CPU-only/no-fallback evidence;
- the strict formal report contract.

The runtime preparation parameters must exactly equal `PLAN.json`. The final report is accepted only
when it is strict `PASS`, `CPU_FORMAL`, and `formal_runtime_certification=true`.

After success, the controller writes `TARGET_EXECUTION_REPORT.json`. This report is derived from the
three-event chain and retains:

```text
holdout_opened=false
prospective_opened=false
public_registration_performed=false
oof_executed=false
```

Its existence before CPU_FORMAL, or any later modification, fails verification.

## CLI

```bash
python scripts/manage_kdpp_fixed_k_target_execution.py prepare \
  --exporter-repo /absolute/exporter-worktree \
  --exporter-head <PR106_HEAD_SHA> \
  --exporter-python /absolute/exporter-python \
  --kdpp-repo /absolute/kdpp-worktree \
  --kdpp-head <THIS_PR_HEAD_SHA> \
  --kdpp-python /absolute/kdpp-python \
  --workspace /absolute/external/run-root \
  --run-id kdpp-target-YYYYMMDD-HHMMSS \
  --game loto7 \
  --prediction-length 1 \
  --config-sha256 <64_HEX>
```

Then follow `COMMANDS.json` in order. The ledger commands are:

```text
record-source
record-history
record-runtime
verify
```

## Verification boundary

Local tests use immutable synthetic fixtures and temporary Git repositories. They validate control
logic, event chaining, deterministic command generation, artifact revalidation, and fail-closed
behavior. They are not production database, PyArrow, human approval, model inference, or hardware
evidence.

Formal success still requires the real target-host sequence and substantive review of every retained
artifact. Public registration, OOF, Holdout, Prospective, and accuracy evaluation remain separate
future phases.
