# Loto Forecast Platform

時系列予測の研究・評価・再現・予測固定・運用証拠化を扱うプラットフォームです。

現在のpackage version、テスト件数、coverage、モデル総数、Git HEADなどの変動値はREADMEへ手書きしません。package versionの正本は`loto.version.__version__`とpackage metadataです。現在状態は実行時に生成された証拠またはmachine-readableな正本から確認します。

## Documentation authority

現在のrepository-wide文書入口は[`docs/README.md`](docs/README.md)です。

文書の`CURRENT` / `HISTORICAL` / `GENERATED`等の扱いは[`docs/DOCUMENTATION_CONTRACT.md`](docs/DOCUMENTATION_CONTRACT.md)に従います。過去の検証レポートに記録されたテスト件数、モデル件数、merge状態などは、その時点のhistorical evidenceであり現在値ではありません。

主要なcurrent文書:

- [Architecture](docs/ARCHITECTURE.md)
- [Evaluation Protocol](docs/EVALUATION_PROTOCOL.md)
- [Data Contracts](docs/DATA_CONTRACTS.md)
- [Directory Structure](docs/DIRECTORY_STRUCTURE.md)
- [Model Inventory](docs/MODEL_INVENTORY.md)
- [Operations](docs/OPERATIONS.md)
- [Windows Installation](docs/WINDOWS_INSTALL.md)

## Evaluation priority

最優先の予測指標は**Hit@±1**です。

正式な比較では少なくとも次を併記します。

- pooled/element Hit@±1
- 位置別Hit@±1
- 全位置/row Hit@±1
- MAE
- MSE
- RMSE

select-familyゲームではHits@kなどの集合指標も利用できますが、位置予測のHit@±1とは別指標です。

候補モデルは、適用可能なRandom、固定値、平均、中央値、直近値、頻度、統計モデル等のbaselineと同じデータ境界・評価窓で比較します。単一の最良seedだけを根拠に採用しません。

詳細は[`docs/EVALUATION_PROTOCOL.md`](docs/EVALUATION_PROTOCOL.md)を参照してください。

## Time-order and leakage policy

評価は時間順を維持します。

```text
Train -> Validation/OOF -> Holdout -> Prospective
```

Scaler、Encoder、特徴量選択、hyperparameter search等のfit/selectionは許可されたTrain/development境界内で行います。Holdoutは候補調整へ使わず、Prospective predictionはactual判明前に固定します。

未来情報混入、順序違反、重複、欠損、外生変数の`available_at`不明を明示的に監査します。Raw source dataは不変の証拠層として扱い、訂正は新しいversion/snapshotを作ります。

## Prediction lock

Prospective predictionはactualを取り込む前にSHA-256とtimestamp evidenceで固定します。

`src/loto/auto_campaign/prediction_lock.py`はcampaign-level lockを構成し、configuration/data/lineage等のidentityとprediction artifactを結び付けます。lockは改ざん・順序に関する証拠であり、予測精度を証明するものではありません。

## Runtime certification

モデルがcatalog上で利用可能に見えることと、正式にruntime成功したことは別です。

正式なruntime evidenceでは対象経路に応じて、model/revision identity、load、input、inference、output shape、finite値、device、GPU process/VRAM、CPU fallback等を検証します。

provider-neutral foundationは`src/loto/runtime_certification/`にあります。未実行または取得不能な確認項目をPASSとして扱いません。

## Main command surfaces

package metadataで定義されている主要entry pointは次です。

```text
loto
loto3
loto-auto-campaign
loto-lab
loto-integrity
loto-github-audit
loto-build-info
```

各commandの利用可否は、対象環境でpackage/dependencyが解決できることを確認した上で判断してください。

## Models and frameworks

モデル件数はREADMEへ固定しません。model catalog/inventoryを正本として確認してください。

対象には統計モデル、機械学習、NeuralForecast系、各種forecasting framework、TSFM/provider adapter等が含まれます。新規モデルを追加する場合も、同一データ境界・同一評価protocol・baseline比較・multi-seed/OOF evidenceを優先します。

## Reproducibility

実験証拠は可能な限り次を固定・追跡できる形にします。

- Run ID
- resolved configuration
- data snapshot/hash
- code hash / Git commit
- model ID / immutable revision
- seed
- OOF/Holdout/Prospective evidence
- predictions and actuals
- evaluation metrics
- runtime/device logs
- SHA-256 manifests

利用するstorage backendはworkflowごとに異なり得ますが、保存先の違いによって証拠契約を弱めません。

## Portability

WindowsとLinuxはrepository操作・検証の明示的なportability対象です。path separator、shell、line ending、case sensitivity、temporary directory、systemd/WSL、CUDA/GPU stack等のOS依存をcore contractへ混入させないことを目標とします。

ただし現在のroot dependency graphには`triton==3.5.1`がunconditional dependencyとして存在するため、Windowsのroot環境解決はplatform remediation対象です。環境が異なる状態で「同じruntime認定済み」とは扱いません。

## Historical documents

以下は重要なhistorical evidenceですが、現在のrepository-wide statusではありません。

- [`docs/IMPLEMENTATION_STATUS_V3.md`](docs/IMPLEMENTATION_STATUS_V3.md)
- [`specs/001-full-coverage/plan.md`](specs/001-full-coverage/plan.md)
- [`VERIFICATION_REPORT.md`](VERIFICATION_REPORT.md)

これらの過去の数値やmerge stateは、現在値へ見せるために上書きしません。

## Scientific position

本softwareは時系列予測手法を比較・検証する研究基盤です。宝くじの当選能力や将来の予測優位性を、モデルの存在や単一runの結果だけから主張しません。

改善が確認できない場合に`NO_MODEL_BEATS_BASELINE`やchampionなしを表現できることも、評価基盤の必要な挙動です。
