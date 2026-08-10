# Current Model Execution Addendum

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:32+09:00
repository: arumajirou/loto_forecast_platform
source_of_truth: merged code + exact-SHA runtime/CI evidence
superseded_by: NONE
```

This addendum records the current execution surface added after the detailed code-grounded snapshot in `MODEL_EXECUTION_MATRIX.md`. It does not rewrite older provider/runtime observations.

## New canonical development campaign

PR #248 merged the following route:

```text
uv run loto3 campaign
  -> loto.cli_v3
  -> loto.evaluation.unified_campaign_cli
  -> loto.evaluation.unified_campaign
  -> catalog_full.build_catalog() for broad planning
  -> RuntimeModel and/or PositionSeriesWorker for compatible routes
  -> explicit fail-visible status for incompatible/non-routable routes
```

This route is distinct from both:

```text
uv run loto experiment research --config ...
  -> orchestration/research.py

uv run loto3 research ...
  -> orchestration/research_v3.py
```

The merged campaign does not retroactively make the older `research.py` implementation game-agnostic.

## Six-game geometry

The unified campaign uses `loto.game.geometry` for:

- `mini` — 5 select positions;
- `loto6` — 6 select positions;
- `loto7` — 7 select positions;
- `bingo5` — 8 select positions;
- `numbers3` — 3 ordered digits;
- `numbers4` — 4 ordered digits.

Model adapters receive game-specific position columns. Digit games preserve order/repetition; select games preserve distinct ascending legality.

## Coverage versus execution

The broad catalog remains an inventory surface. The campaign records every requested `catalog model × game` pair exactly once, but the terminal result may be:

```text
SUCCEEDED
PARTIAL_SEEDS
FAILED
UNAVAILABLE
NOT_ROUTABLE
UNSUPPORTED_GAME
NON_STANDALONE_METHOD
```

Therefore:

```text
174 registered
!= 174 shared-routable
!= 174 runtime-certified
!= 174 × 6 successful executions
!= 174 OOF-evaluated
!= 174 promotable
```

Reconciliation methods remain visible as non-standalone methods rather than being misclassified as independent forecasters.

## Common scientific fields

The unified campaign fixes the primary tolerance to Hit@±1 and records:

- Hit@±1;
- per-position Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE;
- full configured seed results;
- mean, population variance and worst-seed/worst-value statistics;
- mandatory baseline comparisons.

Mandatory baseline families are random, fixed, mean, median, last, frequency and statistical AR(1).

## Prediction sealing

For each game/candidate/seed, prediction evidence is written with `actuals_known=false`, flushed and SHA-256 sealed before the scoring stage reads the corresponding target actuals. Output directories are single-use.

This is development/OOF-style evidence. Holdout and Prospective remain separate closed gates.

## Runtime interpretation

A catalog row is not considered runtime-certified solely because it can be planned. Real runtime certification still requires the relevant model/provider to demonstrate the applicable load, input, inference, finite output, shape, device, GPU/VRAM/PID and fallback/reload evidence.

Existing provider-specific runtime evidence remains authoritative for the exact identity it certifies. The unified campaign is the comparison adapter, not a mechanism for upgrading old runtime evidence classes.

## Merged implementation evidence

```text
PR=248
merge_sha=aae45ba9294499f51cc5f1564de1c6ccf5814230
exact_premerge_head=c7c8a039e7aa1aef34fbfd0af8dc2c41f67945a2
linux_ci_run=31371724178 SUCCESS
windows_portability_run=31371724143 SUCCESS
```

See `UNIFIED_EVALUATION_CAMPAIGN.md` for commands and artifact layout.
