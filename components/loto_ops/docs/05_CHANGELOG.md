
## v0.1.9

- Fixed scheduled pipeline progress status handling: optional full package step can now be marked as `skipped` without failing `schedule-run-now`.
- Kept CLI minimal dependency split introduced in v0.1.8.

# 改修履歴

## 2026-05-23

### 追加

- `loto_ops_pipeline` 統合運用プロジェクトを新設
- `run_id` / manifest / JSONLログ設計を追加
- SQLite→CSV→PostgreSQL `\copy` ロード方式を正式採用
- Streamlit Web UIを運用作業台として設計
- light/full ZIP成果物作成機能を追加
- systemd user timerの日次実行設定を追加

### 修正方針

- `exog_pipeline.py` の `sqlalchemy_inspect` import不足を診断・自動パッチ対象にした
- exog未作成でも統合成功に見える問題を品質ゲートで検出する設計に変更

## 2026-05-23 patch-002

### 修正
- `loto-ops build-dataset` が upstream の `create_loto_forecast_dataset.py` の PostgreSQL `to_sql` 失敗で停止する問題を修正。
- SQLite の `dataset_loto_y_ts` / `dataset_loto_hist_feat` が作成済みで非空なら、build-dataset は成功扱いにする。
- PostgreSQL投入は `loto-ops load-postgres` の `psql \copy` 方式を正式経路として固定。
- nested `uv` 実行時の `VIRTUAL_ENV` 不一致警告を抑制。

### 理由
- upstream スクリプトは SQLite 作成後に大量 `INSERT` 形式の PostgreSQL 書き込みを行い、そこで失敗することがある。
- `loto_ops_pipeline` では COPY ロードを責務分離済みのため、build-dataset の成功条件は SQLite 作成完了にするのが正しい。


## v3 performance

### 追加
- `FastDatasetBuilder` を追加し、legacy PostgreSQL `to_sql` 経路を回避
- `FastCopyLoader` を追加し、ゲーム別パーティションCSV + 並列 `psql \copy` に対応
- `build-dataset-fast`, `load-postgres-fast`, `run-all-fast`, `benchmark-probe` コマンドを追加
- `docs/10_PERFORMANCE_DESIGN.md` を追加
- `polars`, `pyarrow`, `joblib` を依存関係に追加

### 変更
- 通常COPYでも staging table を `UNLOGGED` に変更
- インデックス作成はCOPY後に実行する方針を明文化

### 目的
- CPU使用率が低い直列処理を減らし、DB投入を巨大INSERTからCOPY中心に変更する


## v3.1

### 修正
- `build-dataset-fast --engine auto` で `pd.NA` を含む object dtype に対して `expanding().mean()` が失敗する問題を修正。
- 履歴特徴量生成時の欠損系列を `float64` + `np.nan` に統一。
- `nums` 空ケースと bonus 系列も `float64` に統一。

## v0.1.2

### 追加
- `activate_env.sh` を追加し、プロジェクト直下から `source ./activate_env.sh` で仮想環境を有効化できるようにした。
- `scripts/activate_env.sh` を追加し、scripts配下からも同じ有効化を行えるようにした。
- `scripts/setup_and_activate.sh` を追加し、`.venv` が無い場合の `uv sync` と有効化を1手順で実行できるようにした。
- `scripts/enter_env.sh` を追加し、有効化済みの新しいbashを開けるようにした。
- `docs/11_VIRTUAL_ENV.md` を追加した。

### 修正
- `fast_dataset_builder.py` に `import numpy as np` を追加し、`np.nan` 利用時の `NameError` を修正した。
- `admin.py` の `\gexec` 文字列をエスケープし、Python 3.13 の `SyntaxWarning` を抑制した。


## v0.1.3

### 修正
- `loto-ops webapp` に空きポート自動検出を追加。
- `--auto-port` / `--no-auto-port` / `--port-scan` / `--host` を追加。
- `scripts/open_webapp.sh` を自動ポート選択対応に変更。

### 背景
- Streamlit の `Port 8520 is not available` でWebアプリ起動が止まる問題を回避。

## v0.1.4 / v3.4

### 修正
- `overview.py` の `from __future__ import annotations` が先頭以外に移動して発生する SyntaxError を回避。
- Overview の行数表示を品質レポート依存ではなく PostgreSQL の正確な `COUNT(*)` 直読に変更。
- Streamlit の `use_container_width` 警告に対応し、`width="stretch"` を使用。

### 追加
- `loto-ops recover-base-tables --jobs N` を追加。SQLite成果物から `dataset.loto_y_ts` と `dataset.loto_hist_feat` を再投入する復旧用コマンド。


## v3.8 - Performance architecture redesign

- Added `build-unified-fast` using PostgreSQL CTAS instead of pandas/to_sql.
- Added `light / full / auto` execution modes.
- Added `perf-status`, `exog-mode`, `optimize-db`, and `benchmark-stages` CLI commands.
- Added Resource Governor to select Polars threads, COPY jobs, and exog workers.
- Updated `run-all-fast` to use the fast unified builder by default.
- Updated cron/systemd scheduled run to use `LOTO_OPS_MODE=light` and fast unified build.
- Updated Streamlit Pipeline Run and Settings pages for mode selection and performance diagnostics.
- Added `docs/14_PERFORMANCE_REDESIGN.md`.


## v3.9 - Network timeout safe setup

- Streamlit/Plotly を `web` optional extra に分離。
- `setup_uv.sh` を `--no-dev` CLI最小構成に変更。
- `setup_web.sh` を追加。
- `loto-ops` console script が欠けた場合、自動ラッパーを作成。
- `activate_env.sh` がコマンド存在を実際に検証するよう修正。


## v3.11 / 0.1.10

- cron/systemd/KDE autostart 用に `PATH` を固定し、`uv` 未検出を防止。
- `UV_BIN` 環境変数または `shutil.which("uv")` から子プロジェクト実行用 `uv` を解決。
- `progress.json` を実行開始時に初期化し、前回実行の step timestamp が混ざる問題を修正。
- cron `@reboot`、Kubuntu systemd user、KDE autostart の多重起動を cooldown で抑制。
- Kubuntu 起動直後のDNS未準備対策として systemd 60秒、desktop autostart 120秒の遅延を追加。

## v3.12

- Gmail/SMTP通知を追加。
- Slack Incoming Webhook通知を追加。
- `notify-run-summary` CLIを追加。
- `notify-test` CLIを追加。
- `configs/notify.env.example` を追加。
- `scripts/test_notify.sh` を追加。
- scheduled pipeline終了時に成功/失敗サマリーを自動通知。
