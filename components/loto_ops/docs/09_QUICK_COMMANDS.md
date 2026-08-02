# クイックコマンド

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/setup_uv.sh
uv run loto-ops preflight --auto-fix
uv run loto-ops init-db
uv run loto-ops scrape --games all
uv run loto-ops build-dataset
uv run loto-ops load-postgres
uv run loto-ops build-exog
uv run loto-ops build-unified
uv run loto-ops analyze
uv run loto-ops package --mode light
uv run loto-ops webapp --port 8520
```


## 高速モード

```bash
cd /mnt/e/env/ts/loto_ops
uv run loto-ops build-dataset-fast --engine auto
uv run loto-ops load-postgres-fast --jobs 6
uv run loto-ops build-exog --parallel-workers 16
uv run loto-ops build-unified
uv run loto-ops analyze
```

```bash
uv run loto-ops run-all-fast --engine auto --jobs 6 --with-exog --parallel-workers 16 --with-analysis
```
