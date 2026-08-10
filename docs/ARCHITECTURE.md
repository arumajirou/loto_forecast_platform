# 基本設計書 / Architecture

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
audited_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
```

## 1. 設計目標

本基盤は、予測精度だけでなく次を同時に満たすことを目的とする。

- leakage-safeな時系列評価
- Hit@±1-firstの比較可能性
- model/provider交換可能性
- six-game geometryへの拡張性
- runtime evidenceと科学 evidenceの分離
- prediction-before-actual固定
- fail-visibleな全model × game coverage
- 再現可能なRun ID / hash / artifact lineage

## 2. Canonical game geometry

`src/loto/game/geometry.py` をgame shape/legalityの正本とする。

```text
mini      select / 5 positions / 1..31
loto6     select / 6 positions / 1..43
loto7     select / 7 positions / 1..37
bingo5    select / 8 positions / 1..40
numbers3  digits / 3 positions / 0..9
numbers4  digits / 4 positions / 0..9
```

Select familyはascending/distinct legalityを保持し、digit familyは位置順序と重複を保持する。

## 3. 主要コンポーネント

```text
src/loto/
├── game/                  canonical game geometry
├── data/                  canonicalization / validation / dataset access
├── features/              historical/as-of features
├── models/
│   ├── catalog_full.py    broad generated inventory
│   ├── catalog.py         shared executable ModelSpec catalog
│   ├── factory.py         candidate RuntimeModel implementations
│   ├── workers.py         position/foundation execution worker
│   └── providers/         shared foundation/provider registry
├── evaluation/
│   ├── protocol_v2.py     formal result-affecting protocol identity
│   ├── metrics_general.py geometry-aware metrics
│   ├── metric_registry.py mandatory metric/baseline registry
│   ├── seed_summary.py    all-seed aggregation
│   └── unified_campaign.py broad model × game development campaign
├── probabilistic/
│   └── decoder.py         MAP / WITHIN_TAU family-aware decoding
├── orchestration/         older/specialized research orchestration
├── registry/              experiment/release evidence registration
├── observability/         runtime/resource monitoring
├── api/                   FastAPI surfaces
└── events/                structured event/log evidence
```

Provider-specific isolated campaign directories and `environments/**` coexist with the shared worker path. Broad registration is intentionally not the same as shared runtime routing.

## 4. Evaluation architecture

Current canonical development comparison path:

```text
canonical game frame
  -> development/holdout split
  -> chronological rolling folds
  -> EvaluationProtocolV2
  -> mandatory baselines
  -> broad catalog × game planning
  -> route classification
       candidate RuntimeModel
       PositionSeriesWorker / provider
       NON_STANDALONE_METHOD
       NOT_ROUTABLE / UNSUPPORTED / UNAVAILABLE / FAILED
  -> family-aware legalisation/decoder
  -> prediction lock write + fsync + SHA-256
  -> actual read for scoring
  -> Hit@±1-first metrics
  -> all-seed summary
  -> per-game leaderboard / cross-game macro summary
  -> SHA256SUMS
```

Command surface:

```bash
uv run loto3 campaign ...
```

`orchestration/research.py` と `orchestration/research_v3.py` は別の既存research surfaceであり、unified campaignと同一物として扱わない。

## 5. Catalog / routing architecture

### Broad inventory

`catalog_full.py` は広いinventoryを表現する。監査時点のgenerated countは174 entry。

### Shared execution catalog

`catalog.py` は`ModelSpec`を使うshared execution catalog。

### Runtime worker/provider

`factory.py`、`workers.py`、`providers/**` が実行routeを提供する。

したがって:

```text
REGISTERED
!= SHARED_ROUTABLE
!= RUNTIME_CERTIFIED
!= OOF_EVALUATED
!= PROMOTION_ELIGIBLE
```

## 6. Probability/decoder architecture

PR #249でselect-game constrained decoderに`MAP`と`WITHIN_TAU` objectiveを追加した。

PR #250で、確率を持つunified candidate estimator routeをfamily-specific WITHIN_TAU decoderへ接続した。

```text
candidate binary probability matrix
  -> row normalization per slot
  -> distribution identity = row-normalized-slot-binary-probability-v1
  -> family dispatch
       digits -> positional window-mass WITHIN_TAU decode
       select -> legality-constrained WITHIN_TAU DP
  -> legal point prediction
```

Point-only workerに擬似確率分布を生成しない。Point-only routeは明示的なpoint legalisationを継続する。

Decoder/distribution/post-processing identityはprotocol/runtime evidenceへ残し、旧campaign evidenceを新decoder契約へ黙って読み替えない。

## 7. Data and time architecture

Dataは少なくとも次の意味層を区別する。

```text
raw immutable source
validated/canonical development data
features derived as-of eligible history
Holdout closed slice
Prospective future evidence
```

重要な時刻/順序概念:

- source/event time
- availability time when known
- ingestion time
- forecast creation/seal time
- actual availability/read time

未来情報がeligible training/foldへ侵入しないことを最優先する。

## 8. Prediction/evidence architecture

各runは新しいimmutable output directoryを使う。

Unified campaignの主要artifact:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/<game>.json
prediction_locks/<game>/<candidate>/seed-<seed>.json
SHA256SUMS
```

Prediction lockはactual scoring readより先にpersist/fsync/hashする。

## 9. Runtime certification architecture

Runtime certificationはcatalog statusから独立する。

必要な範囲で:

```text
model identity/revision
environment identity
load
input
inference
output shape
finite values
requested vs observed device
GPU PID/VRAM
CPU fallback
reload/reproducibility
artifact/code/data hashes
```

を証拠化する。

## 10. Deployment / portability

- `uv`, `pyproject.toml`, `uv.lock` をPython environmentの正本とする。
- Linux self-hosted CIがfull repository test laneを持つ。
- native Windows portability laneでlock resolution / wheel build / importを検証する。
- GPU runtime certificationは対象provider/modelごとの実証を必要とする。
- 特定workstationの一時状態をarchitecture contractへ固定しない。

## 11. Scientific gates

```text
IMPLEMENTED
-> RUNTIME_CERTIFIED
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
```

各gateは独立したevidenceを必要とする。

Holdout/Prospectiveをunified development campaignが自動で開かない。

## 12. 品質属性

- Reproducibility
- Auditability
- Leakage resistance
- Fail visibility
- Cross-game comparability
- Runtime portability
- Immutable evidence
- Explicit unsupported-state handling
- Minimal privilege / secret hygiene

## 13. 現在の非主張

Architectureが存在することは以下を意味しない。

- 全174 entryのruntime success
- 実データ174 × 6 campaign完了
- decoderによる実OOF改善
- Holdout/Prospective完了
- champion存在
- production promotion
