# Architecture

## Package Boundaries

後続PRの推奨境界:

```text
src/loto/research_sources/
src/loto/benchmark_fingerprint/
src/loto/retrieval_forecasting/
src/loto/covariate_adapters/
src/loto/online_adaptation/
src/loto/adaptive_ensemble/
src/loto/constrained_output/
src/loto/adapters/<model_id>/
src/loto/<model_id>_campaign/
```

再実装禁止:

```text
src/loto/configuration/            # PR #121
src/loto/runtime_certification/    # PR #123
src/loto/data_access_ledger/       # PR #124
```

## Dependency Direction

```text
research_sources
  ↓
configuration
  ↓
data_access_ledger
  ↓
provider adapter
  ↓
runtime_certification
  ↓
evaluation
  ↓
registry / promotion
```

逆方向importを禁止する。

## Runtime Topology

```text
Campaign Controller
  ├─ config/data binding
  ├─ Data Access Ledger events
  ├─ provider subprocess
  │   ├─ isolated environment
  │   ├─ snapshot verification
  │   ├─ native input
  │   ├─ model load/infer
  │   └─ strict response
  ├─ Runtime Certification SDK
  │   ├─ PID/device/VRAM
  │   ├─ shape/finite
  │   ├─ save/reload/replay
  │   └─ evidence seal
  └─ Evaluation Controller
      ├─ OOF
      ├─ baselines
      └─ immutable metrics
```

## Retrieval Topology

各foldでTrainだけからindexを再構築する。

```text
Fold Train → Index Builder → Index SHA
Validation Query → Retriever → top-k IDs/distances
→ RAFT or TS-RAG → prediction
```

candidate futureはTrain内で完全観測済みでなければならない。全期間indexの再利用は禁止。

## Online Topology

```text
state_t → predict_t → lock_t → actual_t → score_t → update_t → state_t+1
```

actual到着前のupdateを禁止する。

## Constrained Output

Numbers3/4はposition partitionごとにexactly one。MiniLoto/Loto6/Loto7はfixed-cardinality、domain、duplicate rejection、sort。

## Artifact Layout

```text
runs/<campaign>/<RUN_ID>/
├── config/
├── source/
├── data/
├── folds/<fold-id>/{seeds,retrieval,runtime,predictions}/
├── metrics/
├── baselines/
├── prediction-lock/
├── actuals/
├── registry/
├── logs/
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

## Security

- downloadとformal runtimeを分離
- snapshot containment、symlink拒否
- remote codeはallowlist、hash、offline review
- secret redaction
- ZIP traversal、duplicate、casefold collision、compression bomb拒否
