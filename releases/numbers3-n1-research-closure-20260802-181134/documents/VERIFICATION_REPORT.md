# VERIFICATION REPORT

## Conclusion

正式合格モデルは0件です。Production modelは登録しません。
90%目標は終了、35%目標は未達として記録します。

## Dataset

- Rows: 7039
- Range: 1994-10-07 00:00:00 to 2026-07-31 00:00:00
- SHA-256: `d2c599f24ef457e7a66d4607fe475c61c8900197c867b2e00fc172f58fa48355`

## Evidence summary

- F0c: `CLOSE_90_PERCENT_RESEARCH`, best mean Hit@±1=0.31320000000000003
- F1a: Hit@±1=0.302
- F1b: Hit@±1=0.288, continue=False
- F2a: best=multinomial_logistic_calibrated_hit, Hit@±1=0.34
- F2b: `REJECT_F2_LOGISTIC_AS_FORMAL_MODEL`, mean Hit@±1=0.3

単一Holdoutの結果だけでは成功を宣言しません。
