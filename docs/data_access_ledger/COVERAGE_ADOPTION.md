# Coverage build and auto-research adoption

Status: `STACKED_ADOPTION / OPT_IN / PROTECTED-TEST CLOSED`

This lane instruments `src/loto/coverage/runner.py` and
`src/loto/coverage/auto_research.py` without changing either existing module.
The two audited sources are pinned to their Git blob identities:

```text
coverage runner: 8a09c5deab4798bbe604c732f797d9746af84b77
auto research:   e2dbdb3d10c49f81eb80ac7c53f4d66ec7835a20
```

Any source drift blocks execution before the experiment starts.

## Protected-test boundary

The instrumented lane first performs a binary line-count scan to locate the
configured protected-test suffix. Pandas then loads only rows before that boundary.
Protected-test number fields are not numerically decoded or materialized as target
arrays. Certification functions that open the protected test are deliberately not
wrapped or called.

The accessible prefix is not a memory sandbox: calibration and validation rows may
already reside in memory. The evidence guarantees the instrumented model-call and
target-materialization order, not absence from process memory.

## Runtime order

For every calibration and validation fold, the recorder emits:

```text
FIT_MODEL(TRAIN only)
PREDICT(target-free validation identity)
READ_ACTUALS(after prediction)
SCORE
```

Every fold ID includes experiment, model, phase, row, and seed identity. The final
ledger is sealed and revalidated by Data Access Ledger v1.

## Coverage build lane

`run_coverage_experiment_with_ledger` preserves the existing deterministic point
forecast, conformal radius, candidate-pool generation, greedy selection, calibration
metrics, and validation metrics. It never invokes `certify_coverage_experiment`.

Artifacts include:

- `prediction_set.csv`
- `prediction_set.json`
- `selection_trace.json`
- `coverage_summary.json`
- `coverage_data_access_ledger.json`
- `coverage_data_access_validation.json`
- `coverage_data_access_report.json`

## Auto-research lane

`run_auto_research_with_ledger` is intentionally narrower than the legacy runner:

```text
resume=false
local_llm.enabled=false
output directory is new and empty
any experiment failure blocks the run
```

Resume is rejected because previous state and candidate artifacts would introduce
untracked reads. Local-LLM proposal generation is rejected because a dynamic external
proposal source is outside this foundation lane. A later integration may add explicit
proposal provenance and request/response hashes.

Each supported game receives its own ledger under:

```text
<data_access_output>/data_access/<game>/
```

The lane never invokes `certify_auto_research`.

## CLI

```bash
uv run python scripts/run_coverage_with_ledger.py build \
  --config /absolute/path/coverage.yaml

uv run python scripts/run_coverage_with_ledger.py auto \
  --config /absolute/path/auto-coverage.yaml
```

## Fail-closed conditions

Execution or finalization is blocked for:

- source-pin mismatch;
- symlinked config, input, output, or artifact path;
- nonempty output directory;
- insufficient chronological prefix;
- missing or non-monotonic `draw_date`;
- out-of-range or unordered number rows in the accessible prefix;
- actual read before prediction;
- score before actual read;
- missing prediction, actual, or score evidence;
- resume or local LLM in auto research;
- any auto-research experiment failure;
- Data Access Ledger validator findings.

## Non-claims

- no protected Holdout/test certification;
- no future-draw Prospective prediction;
- no Prediction Lock or trusted timestamp;
- no Actual Source certification;
- no Registry, MLflow, artifact publication, promotion, or production binding;
- no real performance certification;
- no claim that accessible calibration/validation targets were absent from memory.
