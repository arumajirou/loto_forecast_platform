# nf_loto_webui

NeuralForecast AutoModels を使って PostgreSQL 上のロト系テーブルから
時系列予測実験を実行・管理するための WebUI / 実験基盤です。

- データソース: PostgreSQL (`nf_loto%` テーブル)
- 実験エンジン: NeuralForecast Auto* + Ray Tune / Optuna
- UI: Streamlit
- ログ/監視: PostgreSQL (nf_model_runs), psutil ベースのリソース計測

このディレクトリは ChatGPT によって自動生成されたテンプレート実装です。
ローカル環境で動かす際は `config/db_config.py` の接続情報を確認してください。


## v1.0.1

- Future target features are generated from an appended unlabeled row.
- Model configuration/state hashes and training cutoff metadata are recorded.
- Duplicate schema 1.1 locks for the same target/cutoff/data are rejected.
- CURRENT lock links are maintained automatically.
