# Profile A/B Testing

## Template audit

```bash
uv run --extra harness loto-harness profile-audit MODEL \
  --modes generic,fast,quality,reasoning,tools \
  --output /ABSOLUTE/PATH/profile-audit.json
```

The report proves which profile was resolved, which request fields changed,
and which changes reached the engine request.

## Effect test

```bash
uv run --extra harness loto-harness profile-ab MODEL \
  --modes generic,fast,quality,reasoning,tools \
  --repetitions 5 \
  --context-tokens 16384 \
  --context-utilization 0.50 \
  --output /ABSOLUTE/PATH/profile-ab.json
```

The evaluator runs the same matrix for every mode. It does not lower the
acceptance threshold when a candidate fails.

## Reading a report

- `achievement_rate`: weighted correctness/achievement score.
- `achievement_delta_vs_generic`: candidate improvement or regression.
- `stability_score`: consistency across task categories.
- `median_latency_seconds`: task-level latency.
- `cache_hit_rate`: cached prompt tokens divided by prompt tokens.
- `applications`: exact transformed request for every task.
- `candidate_beats_generic`: true only when a non-generic mode scores higher.
- `best_mode_meets_gate`: true only when the best mode reaches 0.80.

## Promotion gate

Do not change the production default automatically. Promotion requires:

1. profile A/B report verified by SHA-256;
2. candidate achievement rate at least 0.80;
3. positive delta versus generic;
4. no material tool/schema/coding regression;
5. acceptable latency and token-cost change;
6. human approval before production routing changes.


## V4.2 strict evidence and gates

V4.2 adds `--seed` (default `1`) and records the block/task execution order.
Each trial records masked response/reasoning excerpts, full-text SHA-256, latency,
tokens, finish reason, and criterion-level results. Reasoning stores both
`correctness` and `format_compliance`; task success remains strict and requires both.

A mode is eligible only when its weighted achievement is at least 0.80 and every
critical task meets its configured floor. `best_observed_mode` may identify the
best measured but ineligible mode; `best_mode` is null unless an eligible mode exists.
Automatic promotion remains disabled.

Legacy V4.1 reports can be rejudged without mutation:

```bash
python3 /ABSOLUTE/WORKTREE/scripts/harness/rejudge_profile_ab.py \
  /ABSOLUTE/PATH/legacy-report.json \
  /ABSOLUTE/PATH/strict-judgment.json
```

Because legacy reports do not contain response excerpts, a live V4.2 rerun is
required to distinguish reasoning correctness from formatting failure.

## V4.3 capability versus contract analysis

V4.3 records:

- `semantic_achievement_rate`;
- `contract_achievement_rate`;
- `semantic_success_rates` by task;
- `contract_success_rates` by task;
- `task_failure_classification` with `VERIFIED`, `MODEL_CORRECTNESS`,
  `OUTPUT_CONTRACT`, or `MODEL_AND_CONTRACT`;
- `best_semantic_mode_by_task` for diagnostics only.

The strict promotion gate still uses `achievement_rate` and critical-task floors.
`best_semantic_mode_by_task` never changes production routing automatically.
