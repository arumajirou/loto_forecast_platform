# テスト仕様書

## Unit Test

- 設定読込
- run_id / path生成
- COPY SQL生成
- schema contract検査
- 品質ルール検査
- ZIP manifest生成

## Integration Test

- SQLite → CSV → PostgreSQL COPYの件数一致
- `dataset.loto_y_ts` と `dataset.loto_hist_feat` の必須列確認
- exogなし統合時のwarning確認
- exog必須時のfail確認

## E2E Test

- fixture CSVから run-all
- SQLite作成
- PostgreSQL投入
- unified作成
- quality report作成
- ZIP作成

## 受け入れ条件

- `dataset.loto_y_ts` が0行ではない
- `dataset.loto_hist_feat` が0行ではない
- `dataset.loto_y_ts_unified` の行数が `dataset.loto_y_ts` と一致
- ZIP内に `manifest.json` と `README_UPLOAD.md` が存在
