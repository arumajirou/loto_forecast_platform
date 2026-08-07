# GluonTS P7B target-machine runbook

## 1. Start from a clean committed checkout

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git status --short
git rev-parse HEAD
git branch --show-current
```

P7B refuses formal execution when tracked files are modified. Untracked artifact files do not affect
the tracked-worktree check.

## 2. Run both lanes and the P7 audit

```bash
RUN_ID="gluonts-p7b-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/mnt/e/env/logs/${RUN_ID}"

RUN_ID="${RUN_ID}" \
  bash environments/gluonts-p7b-target-machine.sh \
  "${OUT}"
```

Defaults:

```text
compatibility timeout = 14400 seconds
latest timeout        = 14400 seconds
audit timeout         = 1800 seconds
GPU monitor interval  = 2 seconds
```

Override the limits after the output argument:

```bash
bash environments/gluonts-p7b-target-machine.sh \
  "${OUT}" \
  --compat-timeout-seconds 21600 \
  --latest-timeout-seconds 21600 \
  --audit-timeout-seconds 3600
```

## 3. Resume an interrupted or incomplete run

Use the exact same output directory:

```bash
bash environments/gluonts-p7b-target-machine.sh \
  "${OUT}" \
  --resume
```

P7B verifies source and artifact identity before changing the journal. Completed stages are skipped.
Interrupted or timed-out stage outputs are moved to `history/` before retrying.

Do not use `--resume` after editing source files, switching commits, changing tracked files, or
manually modifying the run artifacts. Create a new run instead.

## 4. Inspect progress and failure classification

```bash
jq . "${OUT}/p7b_execution_journal.json"
jq . "${OUT}/audit/p7_target_machine_audit.json"
jq . "${OUT}/audit/p7_failure_matrix.json"
```

Useful summaries:

```bash
jq -r '.execution_state' \
  "${OUT}/p7b_execution_journal.json"

jq -r '.stages | to_entries[] | [.key, .value.state, .value.return_code] | @tsv' \
  "${OUT}/p7b_execution_journal.json"

jq -r '[.verified_model_lifecycles, .evidence_state, .certification_status] | @tsv' \
  "${OUT}/audit/p7_target_machine_audit.json"
```

## 5. Verify immutable final evidence

A finalized run contains `P7B_EXECUTION_COMPLETE` and `P7B_EXECUTION_SHA256SUMS`.

```bash
(
  cd "${OUT}" || exit 1
  sha256sum -c P7B_EXECUTION_SHA256SUMS
)
```

Opening a finalized run with `--resume` only verifies this inventory and returns the recorded P7 audit
code. It does not run either lane again.

An incomplete run contains `P7B_PARTIAL_SHA256SUMS`. P7B verifies and archives that inventory before
resuming.

## 6. Interpret return codes

```text
P7 audit return code  execution completed; inspect P7 certification/evidence state
3                     preflight, source identity, lock, or audit-interpreter block
124                   P7 audit timeout
130                   interrupted by SIGINT or SIGTERM
```

Compatibility or latest lane non-zero codes are not replaced by a generic supervisor failure. They
remain in the journal and are supplied to P7 for evidence-backed classification.

## 7. Preserve the run

Do not edit, rename, add, or remove files inside a finalized output directory. Copy the complete run
directory when transferring evidence and verify `P7B_EXECUTION_SHA256SUMS` after transfer.
