# データ契約

## 抽選マスター

`draw_id, draw_no, draw_date, n1..n7, bonus1?, bonus2?, available_at`

## 位置表

`draw_id, draw_no, draw_date, position, number, available_at`

## 37候補表

`draw_id, draw_no, draw_date, candidate_number, selected, position_if_selected, available_at`

## 特徴量表

`draw_id, draw_no, candidate_number, freq_w10, freq_w30, freq_w100, freq_all, freq_exp, gap_draws, candidate_scaled, selected`

## 不変条件

- 同一data_versionの入力内容は変更しない
- 訂正は新data_version
- schema_versionを持つ
- available_at不明の外生変数はprohibited
