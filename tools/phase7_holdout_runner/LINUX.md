# Phase 7 Linux execution

Linux execution is repository-owned through `bash tools/phase7.sh`.

The Linux launcher does not search the machine for historical evidence. It uses one explicit evidence root and verifies the frozen SHA-256 identities before provisioning a runtime or executing Replay/Holdout.

Default evidence root:

```text
/mnt/e/env/ts/phase7_evidence
```

Override with:

```bash
export PHASE7_EVIDENCE_ROOT=/path/to/evidence
```

Required layout:

```text
$PHASE7_EVIDENCE_ROOT/
  automlforecast-phase7-holdout-20260818-101611/
  automlforecast-phase6c-ensemble-freeze-20260818-101021/
  automlforecast-phase3-input-size-20260817-173808/
  numbers3-current-canonical-path.txt
```

If the canonical pointer contains a Windows-only path, set the Linux canonical file directly:

```bash
export PHASE7_CANONICAL_PATH=/path/to/the/exact/canonical/file.csv
```

The canonical file is accepted only when its SHA-256 is the frozen identity.

## Commands

```bash
bash tools/phase7.sh status
bash tools/phase7.sh runtime
bash tools/phase7.sh preflight
bash tools/phase7.sh replay
bash tools/phase7.sh holdout
```

`holdout` automatically requires a current Linux Replay certificate. If the certificate is absent or no longer matches repository/evidence/runtime identity, the launcher runs Replay-only first. Holdout remains blocked unless the 4-seed / 80-trial Replay completes with zero Holdout and zero Actual access.

The Linux runtime is isolated under `$PHASE7_RUNTIME_ROOT` (default `$HOME/.cache/loto-phase7-linux-v1`) and uses `uv` with pinned top-level package versions recorded in `linux-runtime-requirements.txt`. Resolved packages are frozen into the runtime directory after installation.

The historical Windows evidence is never overwritten. A persistent compatibility HOME contains symlinks to immutable evidence and new Linux-only replay/Holdout outputs. This also preserves the existing sealed-Holdout rerun guard across invocations.

During Holdout the shell launcher polls `artifacts/progress.json` and displays a 0-100% progress bar using `holdout_draws_done / 50`, together with `actuals_accessed / 50`.

If Holdout stops after any prediction lock or Actual access, do not rerun it. Inspect `RUNNER_TERMINAL_STATE.json` and the printed terminal output first.
