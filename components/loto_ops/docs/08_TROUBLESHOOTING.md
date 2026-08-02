# トラブルシューティング

## exog生成で `sqlalchemy_inspect` が未定義

```bash
uv run loto-ops preflight --auto-fix
```

または手動で以下を追加する。

```python
from sqlalchemy import inspect as sqlalchemy_inspect
```

## PostgreSQL投入が遅い/失敗する

`pandas.to_sql(method="multi")` ではなく `uv run loto-ops load-postgres` のCOPY方式を使う。

## unifiedはできたがexogが無い

`--allow-no-exog` では警告として許可される。完全版が必要なら `--with-exog` で実行する。

## build-dataset が SQLAlchemy e3q8 / 大量 INSERT で失敗する

### 症状
`create_loto_forecast_dataset.py` が SQLite 作成後、PostgreSQL へ `pandas.to_sql(method="multi")` で書き込もうとして失敗する。

### 対応
`loto_ops_pipeline` では PostgreSQL への正式投入は `loto-ops load-postgres` の `psql \copy` 方式です。`build-dataset` は SQLite の以下2テーブルが存在し非空なら成功扱いにします。

- `dataset_loto_y_ts`
- `dataset_loto_hist_feat`

### 推奨実行順

```bash
uv run loto-ops build-dataset
uv run loto-ops load-postgres
```


## Webアプリのポートが使用中の場合

症状:

```text
Port 8520 is not available
```

対応:

```bash
loto-ops webapp --port 8520 --auto-port
```

使用中のプロセス確認:

```bash
ss -ltnp | grep ':8520' || true
lsof -iTCP:8520 -sTCP:LISTEN -P -n || true
```

既存Streamlitを停止する場合:

```bash
pkill -f 'streamlit run .*loto_ops/webapp/app.py' || true
```
