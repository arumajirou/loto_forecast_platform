# Moirai 2.0 Handoff

PR #83 is the P0-P6 base, PR #86 is P7, PR #87 is the P8 certifier, PR #89 is P8A, PR #91 is
P8B, and P8C continues only on `feat/moirai2-runtime-evidence-gate-v1`. Do not retarget or write to
any parent branch.

## 1. Complete the P8B reviewed-lock workflow

Generate a new candidate outside the runtime lane, inspect the dependency graph, sources, hashes,
licenses, and warnings, dry-run installation, and apply only after explicit human approval.

```bash
uv run python scripts/generate_moirai2_lock_candidate.py \
  --runtime-lane supported-py311 \
  --python 3.11 \
  --output-dir artifacts/moirai2/lock-candidate/<RUN_ID>
```

Install the exact approved candidate using `scripts/install_reviewed_moirai2_lock.py`. Preserve the
candidate, dry-run, apply, backup, review, approval, manifest, and SHA evidence. Repeat independently
for `cuda13-experimental`.

## 2. Run the supported campaign through the P8C wrapper

The repository worktree must be clean. The wrapper captures the source commit, source tree, and
principal file hashes before running the existing P8A campaign. Use a new immutable output directory.

```bash
uv run python scripts/run_moirai2_runtime_campaign_p8c.py \
  --campaign-id <CPU_RUN_ID> \
  --runtime-lane supported-py311 \
  --device cpu \
  --snapshot-path /absolute/path/to/pinned/snapshot \
  --output-dir artifacts/moirai2/runtime-campaign/<CPU_RUN_ID>
```

Do not invoke `run_moirai2_runtime_campaign.py` directly for formal evidence. Direct P8A outputs do
not contain the P8C source and launch seal required by the independent verifier.

## 3. Run the CUDA13 campaign through the same wrapper

Use the same source commit and pinned model snapshot. Cases remain strictly serial.

```bash
uv run python scripts/run_moirai2_runtime_campaign_p8c.py \
  --campaign-id <CUDA_RUN_ID> \
  --runtime-lane cuda13-experimental \
  --device cuda \
  --snapshot-path /absolute/path/to/pinned/snapshot \
  --output-dir artifacts/moirai2/runtime-campaign/<CUDA_RUN_ID>
```

Preserve all requests, responses, run evidence, GPU monitor samples, stdout/stderr, exit codes,
source identity, launch evidence, artifact manifests, and SHA256SUMS.

## 4. Independently verify the paired evidence

Run the verifier into a third new directory. Pin the expected source commit explicitly.

```bash
uv run python scripts/verify_moirai2_runtime_evidence.py \
  --supported-campaign-dir artifacts/moirai2/runtime-campaign/<CPU_RUN_ID> \
  --cuda-campaign-dir artifacts/moirai2/runtime-campaign/<CUDA_RUN_ID> \
  --expected-source-commit "$(git rev-parse HEAD)" \
  --output-dir artifacts/moirai2/runtime-evidence-gate/<VERIFY_RUN_ID>
```

Review `P8C_RUNTIME_EVIDENCE_REPORT.json` and `SHA256SUMS`. P9 may be opened only when:

```text
status=PASS
p9_oof_gate_open=true
formal_campaign_count=2
formal_case_count=12
provider_process_evidence_count=24
same_source_across_lanes=true
same_model_artifact_across_lanes=true
all_manifests_verified=true
all_native_quantiles_verified=true
all_reload_pairs_verified=true
all_cuda_external_gpu_evidence_verified=true
```

CPU-versus-CUDA exact prediction equality is recorded but is not a formal gate. Do not claim model
accuracy, open OOF, Holdout, or Prospective, or promote the model based only on runtime evidence.
Keep all stacked PRs Draft until real evidence, Ruff, mypy, focused tests, one final full pytest, and
one actionable GitHub Actions run pass.
