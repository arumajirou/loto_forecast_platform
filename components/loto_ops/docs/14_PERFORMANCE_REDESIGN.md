# v3.8 Performance Redesign

## 結論

v3.8では、リソースを無理に最大使用するのではなく、ボトルネックごとに処理方式を分離した。
特に `build-unified` の `pandas/to_sql` 経路を避け、PostgreSQL内部の `CREATE TABLE AS SELECT` で結合と保存を行う。

## 主な変更

- `light / full / auto` モードを追加
- 日次運用は `light` を標準化
- `build-unified-fast` を追加
- `build-unified --engine fast` を標準化
- `perf-status` でCPU/メモリ/DB/テーブルサイズを診断
- `exog-mode light/full/status` で重いexogテーブルを退避・復元
- `run-all-fast --mode light --package light` を日次向けに推奨
- cron/systemdでは `LOTO_OPS_MODE=light` を標準値に設定

## なぜ速くなるか

旧方式:

```text
PostgreSQL -> pandas DataFrame -> pandas merge -> to_sql -> PostgreSQL
```

新方式:

```text
PostgreSQL内部で CTAS JOIN -> INDEX -> ANALYZE
```

Pythonへの巨大データ転送と `to_sql` の待ち時間を減らす。

## 推奨コマンド

```bash
cd /mnt/e/env/ts/loto_ops
source ./activate_env.sh

loto-ops perf-status --mode auto
loto-ops run-all-fast --mode light --with-exog --with-analysis --package light
```

unifiedだけ再作成する場合:

```bash
loto-ops build-unified-fast --mode light
```

研究用の重い横持ちデータセット:

```bash
loto-ops build-unified-fast --mode full --max-exog-cols 256
```

## exogテーブル管理

```bash
loto-ops exog-mode status
loto-ops exog-mode light
loto-ops exog-mode full
```

`light` は `chronos / merlion / pypots / timesfm / uni2ts` を `exog_full` に退避し、
日次処理で `exog.loto_y_ts_exog` だけを使いやすくする。

## 注意

`full` は1000列級になる場合がある。メモリ、PostgreSQL、ディスクI/Oが詰まりやすいため、日次cronには使わない。
