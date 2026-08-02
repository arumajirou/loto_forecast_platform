# 基本設計書

## 全体フロー

```text
preflight
  ↓
init-db
  ↓
scrape
  ↓
build-sqlite
  ↓
quality-before-db
  ↓
load-postgres
  ↓
build-exog
  ↓
build-unified
  ↓
analyze
  ↓
package
```

## 重要設計判断

`raw/interim/processed` CSVをそのまま本番DBに入れず、既存プロジェクトが期待する `dataset.loto_y_ts` と `dataset.loto_hist_feat` を作る。
PostgreSQL投入は `pandas.to_sql(method="multi")` ではなく、SQLite→CSV→`psql \copy` を標準にする。

## exog必須ルール

- `--with-exog`: `exog.loto_y_ts_exog` が存在しなければ失敗扱い
- `--allow-no-exog`: unifiedは作るが警告をmanifestとUIに出す
