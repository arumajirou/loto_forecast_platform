# Detailed Design

## Documentation-Level Interfaces

以下は後続PRで実装する契約設計であり、本PRではコード化しない。

### ResearchSourceRecord

```python
class ResearchSourceRecord:
    source_id: str
    title: str
    paper_url: str
    paper_identifier: str
    official_code_url: str | None
    source_revision: str
    model_repo_id: str | None
    model_revision: str
    code_license: str
    weight_license: str
    commercial_eligibility: str
    trust_remote_code: bool
    required_files: list[ArtifactIdentity]
    verification_status: str
```

revisionはimmutable commit/tagとし、`main`や`latest`だけをformal pinにしない。paper、code、weightのmaintainer identityを照合し、code/weight licenseを分離する。

### ModelIntakeSpec

```python
class ModelIntakeSpec:
    model_id: str
    family: str
    source_id: str
    python_lane: str
    package_requirements: tuple[str, ...]
    supported_games: tuple[str, ...]
    supported_horizons: tuple[int, ...]
    supported_layouts: tuple[str, ...]
    context_min: int
    context_max: int
    context_multiple: int | None
    point_semantics: str
    quantile_levels: tuple[float, ...]
    sample_semantics: str | None
    remote_code_policy: str
```

### BenchmarkFingerprint

dataset、split、cutoff、feature set、baseline inventory、metric contract、compute budget、contamination statusを個別SHA-256で固定する。

### RetrievalIndexManifest

run/fold、Train slice SHA、context/future length、distance、embedding model、item count、observed range、forecast origin、future actual flag、index SHAを持つ。

必須:

- last observed < forecast origin
- target validation foldを含まない
- candidate futureがTrain内で観測済み
- query自身の未来をretrievalしない
- top-k IDと距離を保存

### OnlineUpdateEvent

`state_before → prediction_lock → actual_source → score → update_started → update_completed → state_after`。順序は`prediction < lock < actual <= score < update`。

### PartitionConstraintSpec

universe、partitions、各partitionのexact selection数、total cardinality、duplicate policy、output orderを持つ。Numbers3/4では各partitionから1。通常k-DPPだけで保証できると主張しない。

## Model-Specific Design

### Granite FlowState

- commercial/enterprise向けGranite variantを優先
- SSM encoder + Functional Basis Decoder
- q0.1..q0.9を保持
- sampling-rate/context/horizonを実測
- revision tagを解決commitと全weight hashへ結合
- r1.0/r1.1を混在させない
- history長とminimum contextを照合

### TempoPFN

- 38M checkpoint
- synthetic-only pretrainingをcontamination controlとして記録
- long contextのVRAM/latency
- state-weaving固有のsave/reload可否
- `.pth` loader security review
- source/package importを固定

### Kairos

- 10Mを先行
- 23M/50Mは10Mのruntime/OOF後
- remote code file allowlist、SHA、human review
- dynamic patch routerの選択をevidence化
- positivity/flip averagingを別variantにする

### Reverso-Small

- 公開済み550Kだけを対象
- 2.6M/Nanoは`NOT_AVAILABLE`
- long convolution/DeltaNet依存をisolated envへ閉じ込める
- CPU latency、RAM/VRAM、parameter count
- inference augmentationをvariant分離

### Granite PatchTST-FM

- 通常PatchTSTと別ID
- 約1GB weightのdisk/hash gate
- 99 quantile完全inventory
- point forecastの定義
- 16GB GPUでsafe batch matrix

### LightGTS

- source/model licenseを確定
- remote-code review
- Transformers 4.30.2をisolated laneに限定
- period selectionを保存
- periodicity破壊negative control

### Super-Linear

- official revision、checkpoint、license再確認
- expert数/resampling policyをconfig化
- spectral gate weight保存
- CPU baseline budget
- checkpointがなければreproduction trainingを別PR

## Method Design

### RAFT

no retrieval、neighbor-only、weighted neighbor、model+retrieval、random retrieval negative controlを比較する。

### TS-RAG

base TSFMを固定し、retriever、encoder、ARMを別artifactとして保存。base-only、retrieval-only、ARMを比較し、DBはfold-local。

### Covariate Adapter

past-onlyとknown-futureを分離し、availability timestamp、block shuffle、drop-one、Train-only causal screen、adapter/LoRA/full tuningを別protocolにする。

### Adaptive Ensemble

provider OOF、family、runtime cost、history/uncertainty descriptorを入力にし、target foldをweight fitに使わない。baseline fallback、weight entropy、leave-one-family-out、no-degradation gateを要求する。

## Error Taxonomy

`SOURCE_UNVERIFIED`、`LICENSE_UNVERIFIED`、`REVISION_UNPINNED`、`DEPENDENCY_UNRESOLVED`、`REMOTE_CODE_REVIEW_REQUIRED`、`SNAPSHOT_MISMATCH`、`LOAD_FAILED`、`INFERENCE_FAILED`、`OUTPUT_SHAPE_INVALID`、`OUTPUT_NON_FINITE`、`DEVICE_MISMATCH`、`CPU_FALLBACK_DETECTED`、`GPU_PID_NOT_OBSERVED`、`REPLAY_MISMATCH`、`DATA_LEAKAGE_DETECTED`、`RETRIEVAL_LEAKAGE_DETECTED`、`OOF_INCOMPLETE`、`BASELINE_INCOMPLETE`、`RESEARCH_NO_GAIN`、`HOLDOUT_LOCKED`、`PROSPECTIVE_PENDING`。

## Idempotency

Run ID再利用、immutable output上書き、conflict payloadを拒否する。exact retryは既存receiptを再検証し、partial failureをPASSへ変換しない。
