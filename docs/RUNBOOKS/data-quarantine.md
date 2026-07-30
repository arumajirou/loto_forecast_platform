# Runbook: データ不一致

1. 本番Stageを停止。
2. 公式正本と第二取得元、raw SHA-256を確認。
3. 不一致レコードをquarantineへ移す。
4. Canonicalを上書きしない。
5. 公式訂正確認後、新data_versionを発行。
6. 影響するfeatures/model/forecastを台帳から列挙。
