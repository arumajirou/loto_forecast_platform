# Loto Forecast Platform v3.2.0 — bounded all-model auto-coverage + local LLM loop

## Implemented

- `loto experiment auto-coverage --config ...`
- `loto experiment auto-coverage --config ... --certify`
- Mini Loto, Loto6 and Loto7 geometry support
- finite Cartesian enumeration of every value explicitly declared in `parameter_spaces`
- model/ensemble/window/lag/regularization/candidate-pool/diversity search
- leakage-safe train/calibration/validation/protected-test separation
- walk-forward point forecasting
- empirical residual candidate generation preserving cross-position dependence
- greedy minimum-cardinality coverage selection
- best-of-K row ±1 coverage, element ±1 coverage, best MAE and exact-row metrics
- resumable `state.json`
- append-only `experiments.jsonl`
- per-experiment candidate CSV artifacts
- target-aware stopping, runtime/experiment/failure budgets
- OpenAI-compatible local LLM proposal loop
- strict JSON proposal parsing and catalog validation
- LLM proposals never self-certify; all are measured by the same evaluator
- protected test remains closed until explicit `--certify`
- PowerShell runner with optional data acquisition and LLM disable switch

## Truthfulness boundary

“All settings” is mathematically impossible for continuous and unbounded parameter domains. The implementation therefore evaluates the complete finite Cartesian product explicitly declared in YAML. Optional catalog models whose providers are unavailable fail explicitly and remain in the experiment ledger. They are never silently reported as successful.

The system does not promise that 90% can be achieved. It reports `TARGET_MET` only when validation `row_within_tolerance >= 0.90`. Candidate count is always reported, preventing a misleading claim based on an unbounded prediction set.

## Commands

```powershell
uv sync --frozen --extra dev --extra full
uv run pytest -q
uv run loto data acquire --games mini,loto6,loto7 --output runs/data-acquisition-all --force
uv run loto experiment auto-coverage --config configs/auto_coverage_all_loto.yaml
```

Exhaustive declared available-model mode:

```powershell
uv run loto experiment auto-coverage --config configs/auto_coverage_all_available_models.yaml
```

Final protected-test certification, once only:

```powershell
uv run loto experiment auto-coverage --config configs/auto_coverage_all_available_models.yaml --certify
```

## Verification

- Full pytest suite: 323 passed
- Synthetic Mini Loto/Loto6/Loto7 CLI smoke: passed
- Protected test remains unopened during tuning
