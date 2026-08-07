# P8D Target-Host Orchestration

P8D connects the existing P8B reviewed-lock workflow and P8C runtime evidence gate without
performing automatic approval, installation, or model execution. It creates a target-host control
workspace outside the Git repository and advances only after externally produced evidence passes
its phase-specific validator.

## Control workspace

The preparation command requires a clean source tree, an existing absolute snapshot directory, and
a new workspace outside the repository.

```bash
uv run python scripts/prepare_moirai2_target_execution.py \
  --run-id <RUN_ID> \
  --snapshot-path /absolute/path/to/pinned/snapshot \
  --workspace-dir /absolute/path/outside/repository/<RUN_ID>
```

The control directory contains:

- `P8D_EXECUTION_PLAN.json`;
- `P8D_EXECUTION_STATE.json`;
- `P8D_OPERATOR_COMMANDS.md`;
- immutable checkpoint files for every accepted transition;
- `ARTIFACT_MANIFEST.json` and `SHA256SUMS`.

Runtime artifacts are stored outside the control directory so the control manifest remains small
and deterministic.

## Strict stage order

The only accepted transition order is:

1. supported lock candidate;
2. supported human-approved lock installation;
3. supported CPU six-case campaign;
4. CUDA lock candidate;
5. CUDA human-approved lock installation;
6. CUDA six-case campaign;
7. independent P8C pair verification.

A transition cannot be skipped or repeated. Each accepted event records the full artifact directory
SHA-256, summary, previous-event SHA-256, timestamp, and event SHA-256. Altering an older event breaks
the chain and invalidates the current state.

## Approval boundary

P8D never supplies the reviewer, review time, or approval decision. The generated operator commands
contain explicit placeholders. Installation evidence is accepted only when:

- status is `INSTALLED`;
- `apply_requested=true`;
- reviewer is non-empty;
- review time is timezone-aware;
- installed runtime lane matches;
- candidate and installed lock SHA-256 values match.

A dry-run output cannot be recorded as an installation.

## Campaign and pair validation

Campaign recording calls the P8C campaign verifier again with the expected lane, device, and source
commit. Final pair recording re-runs the CPU/CUDA pair verifier and compares it with the retained
`P8C_RUNTIME_EVIDENCE_REPORT.json`.

`p9_oof_gate_open=true` is written only after all seven events are valid and the pair contains two
campaigns, 12 cases, and 24 provider-process evidence records. No accuracy claim is made.
