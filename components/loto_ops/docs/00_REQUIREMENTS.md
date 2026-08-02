# 要件定義書

## 目的

`loto_life_feature_pipeline` と `loto_forecast_project` を上位から統合し、データ取得・DB作成・特徴量生成・品質検査・Web確認・成果物ZIP化・定期実行までを再現可能にする。

## 機能要件

- DB初期化、スキーマ初期化、安全リセット
- loto-life CSV取得と正規化
- SQLite中間保存
- PostgreSQL `dataset.loto_y_ts` / `dataset.loto_hist_feat` 作成
- exog特徴量生成
- unifiedデータセット生成
- Webアプリでテーブル・品質・成果物を確認
- ブラウザ提出用ZIP作成
- systemd user timer による日次実行

## 非機能要件

- run_id単位の追跡性
- 失敗時に既存成功データを壊さない冪等性
- 危険操作の確認フラグ必須
- JSONLログとmanifestによる可観測性
- ruff/mypy/pytestで保守しやすい構造
