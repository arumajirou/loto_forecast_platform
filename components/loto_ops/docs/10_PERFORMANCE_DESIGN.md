# 高速化・効率化設計 v3

## 結論

`htop` でCPU使用率が低い場合、主因はCPU不足ではなく、処理が直列でDB投入が巨大INSERTに寄っていることです。v3では以下に統一します。

1. `pandas.to_sql(method="multi")` を本番投入経路から外す
2. `UNLOGGED staging table` へ `psql \copy` でロードする
3. CSVを `loto` 単位に分割し、複数 `psql` クライアントで並列COPYする
4. Polarsが使える環境では、縦持ち化・rolling・cumsumをPolarsで実行する
5. インデックスはCOPY後に作成する

## 新コマンド

```bash
uv run loto-ops build-dataset-fast --engine auto
uv run loto-ops load-postgres-fast --jobs 6
uv run loto-ops run-all-fast --engine auto --jobs 6 --with-exog --parallel-workers 16 --with-analysis
```

## 推奨環境変数

```bash
export POLARS_MAX_THREADS=24
export RAYON_NUM_THREADS=24
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_MAX_THREADS=16
```

## ボトルネック調査

```bash
uv run loto-ops benchmark-probe
bash artifacts/reports/system_probe_commands.sh
```

## 期待効果

- DB投入: 巨大INSERTよりCOPYのほうが安定・高速
- 正規化/特徴量生成: Polars使用時にCPUを使いやすい
- exog: `--parallel-workers 16` などでCPU利用率を上げる
- PostgreSQL: `COPY -> index -> ANALYZE -> promote` の順にして待ちを減らす
