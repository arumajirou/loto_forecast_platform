# Numbers3 N1 研究終了・Shadow Prospective 配布版

この配布版は次を実装しています。

- F0c/F1a/F1b/F2a/F2bの最新成功Run探索
- 研究終了パッケージと必須文書生成
- Evidence、Artifact Manifest、SHA256SUMS
- Production modelなしの明示
- 固定値、rolling Dirichlet、Tree depth 4、Multinomial LogisticのShadow予測
- 実測値を含まない予測JSONの事前固定
- データHash、コードHash、Git commit、固定時刻の保存
- 合成データsmoke test

## インストール

```bash
unzip nf_loto_research_closure_v1.0.0.zip
cd nf_loto_research_closure
bash scripts/install.sh
```

## G0a 研究終了パッケージ生成

```bash
PROJECT_ROOT=/mnt/e/env/ts/loto_forecast_platform \
ARTIFACT_ROOT=/mnt/e/env/ts/loto_forecast_platform/artifacts/numbers3 \
DATA=/mnt/e/env/ts/loto_forecast_platform/data/exports/numbers3/numbers3_n1.parquet \
bash scripts/run_g0a.sh
```

## G0b 次回予測の固定

`TARGET_DS`は最新実測日より後の日付にしてください。

```bash
PROJECT_ROOT=/mnt/e/env/ts/loto_forecast_platform \
DATA=/mnt/e/env/ts/loto_forecast_platform/data/exports/numbers3/numbers3_n1.parquet \
bash scripts/run_g0b.sh 2026-08-03
```

## 直接CLI

```bash
uv run loto-research --help
uv run loto-research close --help
uv run loto-research shadow-lock --help
uv run loto-research verify --help
```

## 注意

Shadow予測はProduction modelではありません。実測判明後に作成した予測をProspectiveとして扱わないでください。


## v1.0.1

- Future target features are generated from an appended unlabeled row.
- Model configuration/state hashes and training cutoff metadata are recorded.
- Duplicate schema 1.1 locks for the same target/cutoff/data are rejected.
- CURRENT lock links are maintained automatically.
