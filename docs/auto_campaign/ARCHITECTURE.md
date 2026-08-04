# ARCHITECTURE

## Layers

1. **Contracts** — Pydantic campaign, split, search, resource, and persistence
   configuration.
2. **Registry** — runtime AutoModel membership and signature/default-config
   discovery.
3. **Coverage planner** — Ray-domain decoding, numeric representatives, finite
   categorical coverage, deterministic pairwise planning.
4. **Data tracks** — immutable MiniLoto source normalization and chronological
   U-Shared/U-Local/M-Joint/H-HINT panels.
5. **Execution** — stage/task planner, resource-aware scheduler, OOM retry, Ray
   or Optuna AutoModel construction.
6. **Persistence** — per-successful-Trial checkpoints plus selected
   NeuralForecast bundles, atomic directories, SHA-256.
7. **Verification** — load/predict equality, finite weights/output, device/GPU
   evidence, task/trial counts, complete digest listing.
8. **Evaluation** — Hit@±1-first ranking, per-position and all-position metrics,
   seed aggregation, statistical and simple baselines.
9. **Operations** — resumable CLI, tmux launcher, group/stage progress monitor.

## Stage flow

```text
P0 inventory -> plan -> P1 smoke -> P2 API coverage -> P2 config coverage
-> P3 HPO -> P3 Validation replay -> P4 OOF -> P5 Holdout
-> P6 Prospective -> verification
```

HPO uses only the Train and Validation partitions. Validation replay compares
all successful Trial configurations using Hit@±1. Holdout and Prospective never
feed back into configuration selection.

## Persistence boundaries

Ray and Optuna temporary directories are never authoritative. Each successful
Trial is copied into the campaign task directory with its own checkpoint,
configuration, metrics, load verification, manifest, and SHA-256 listing.
Selected models are stored as both a complete NeuralForecast save and a CPU
`state_dict.pt`.
