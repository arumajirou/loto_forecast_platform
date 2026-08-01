# Full Implementation Quickstart

## Install

```bash
./tools/setup_local.sh
```

## Verify locally

```bash
./tools/verify_full_implementation.sh
```

## 30-fold acceptance campaign

```bash
FOLDS=30 SEEDS=42 ./tools/run_robustness_campaign.sh
```

Expected model/condition rows: 720.

## Formal 100-fold × 3-seed campaign

```bash
FOLDS=100 SEEDS='42 43 44' ./tools/run_robustness_campaign.sh
```

Expected rows: 7,200. This command is intentionally executed on the user's local GPU/LightGBM environment because the uploaded source snapshot does not include the large datasets and runtime services.
