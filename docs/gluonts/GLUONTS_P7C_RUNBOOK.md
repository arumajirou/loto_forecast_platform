# GluonTS P7C runbook

## New target-machine execution and analysis

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

RUN_ID="gluonts-p7c-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/mnt/e/env/logs/${RUN_ID}"

RUN_ID="${RUN_ID}" \
bash environments/gluonts-p7c-target-machine.sh \
  "${OUT}"
```

Exit codes:

```text
0  = all 18 lifecycles verified; P8 eligible
10 = P7 evidence valid but remediation is required
20 = P7 evidence invalid or incomplete; model claims are blocked
2  = P7B/P7C input or execution contract invalid
```

A return code of 10 or 20 is an expected classified result, not an unclassified shell failure.

## Analyze an existing completed P7B run

```bash
P7B_OUT="/mnt/e/env/logs/<P7B_RUN_ID>"
P7C_OUT="${P7B_OUT}-p7c"

bash environments/gluonts-p7c-analyze.sh \
  "${P7B_OUT}" \
  "${P7C_OUT}"
```

Never place `P7C_OUT` inside `P7B_OUT`; doing so would alter the immutable P7B checksum inventory.

## Inspect the queue

```bash
column -ts $'\t' \
  "${P7C_OUT}/p7c_remediation_queue.tsv" \
  | less -S

jq '{
  evidence_state,
  certification_status,
  verified_model_lifecycles,
  p8_eligible,
  counts,
  recommended_next_action
}' "${P7C_OUT}/p7c_remediation_plan.json"
```

## Verify artifacts

```bash
(
  cd "${P7C_OUT}" || exit 1
  sha256sum -c P7C_SHA256SUMS
)
```

## Resume an incomplete P7B run

P7C will not analyze an incomplete P7B execution. Resume P7B first:

```bash
bash environments/gluonts-p7b-target-machine.sh \
  "${P7B_OUT}" \
  --resume
```

Then run the analyze-only command with a new, empty P7C output directory.

## Remediation policy

- Do not modify the source P7B directory.
- Do not rerun only the best-looking seed or model result.
- Keep verified rows immutable and visible.
- Apply code changes only for evidence-backed implementation categories.
- Repair environment/version/import failures before changing model code.
- Use a new Run ID after any code, lockfile, dependency, or configuration change.
- Do not begin P8 unless `p8_eligible` is exactly `true`.
