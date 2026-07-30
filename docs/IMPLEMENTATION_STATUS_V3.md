# Implementation Status v3.0.0

判定日: 2026-07-30 / 総合判定: **VERIFIED (light environment)** + **NOT_CERTIFIED (external deps)**

軽量環境（numpy / pandas / pydantic / scikit-learn / scipy / PyYAML / prometheus-client / fastapi /
pytest / optuna）で実行可能な経路は全て検証済みです。外部サービスと GPU を要する経路は
実装済みだが未認定として明示します。

## 検証済み実測値

| 指標 | 値 | 取得方法 |
|---|---:|---|
| pytest | **313 passed / 0 failed** | `pytest -q`（`--extra dev` のみ） |
| coverage | **75%** (3995/5328 stmt) | `pytest --cov=src/loto` |
| 登録モデル | **174** | `loto3 catalog --counts` |
| 対応ゲーム | **6 / 6** | `test_run_completes_for_every_game` |
| テスト密封性 | optuna 有無で判定同一 | uninstall → rerun で実証 |
| 完全性マニフェスト | 1個 / 自己検証つき | `loto3 integrity check` |

## v2.1.0 検出欠陥への対応

| # | 欠陥 | 対応 | 検証テスト |
|---|---|---|---|
| 1 | `verification/SHA256SUMS` が 14/82 FAILED（旧版残骸） | 削除。`INTEGRITY.json` に一本化し MODIFIED/MISSING/**UNTRACKED** を区別 | `test_added_file_is_reported_as_stale_manifest` |
| 2 | `except Exception` により optuna 有無でテスト判定が変化 | `ImportError` のみに限定し、欠落パッケージ名を出力。optuna を `dev` へ宣言 | `test_api_exposes_runs_events_resources_and_games` |
| 3 | pace_gate / promotion / calibrators / stacking がデッドコード | research 経路へ結線。calibrators は 0% → 100% | `test_pace_gate_is_wired_not_dead_code` |
| 4 | 予測・評価コアが 37/7 ハードコード | `GameGeometry` へ集約。AST ゲートで再発防止 | `test_no_hardcoded_geometry_outside_game_package` |
| 5 | 品質ゲートが来歴列の全NULLを PASS | `data/provenance.py` を追加 | `test_the_exact_v2_defect_is_caught` |
| 6 | 中核 `research.py` が 13.5% | v3 中核を新規実装し全モジュール 80% 超 | 下表 |
| 7 | §5集計が85 vs 総数84 | 件数を計算値化。文書は `loto3 catalog` から生成 | `test_library_subtotals_sum_to_total` |
| 8 | TSFM に repo/revision がなく再現不能 | `repo_id` 付与。未確認SHAは `UNPINNED` 明示（捏造せず） | `test_unpinned_revisions_are_flagged_not_fabricated` |
| 9 | `api/openapi.json`（9 paths）が陳腐化し二重 | 削除し単一化 | — |
| 10 | robots.txt / ToS 未確認 | `data/robots.py`（per-host キャッシュ + crawl-delay + レートリミッタ） | `test_disallowed_url_is_refused` |

## 追加した機能

| 機能 | モジュール | 根拠 |
|---|---|---|
| protocol_hash | `evaluation/protocol.py` | 異条件比較の実行時禁止 |
| 多重比較補正 | `evaluation/multiplicity.py` | 100モデル無補正の FWER は 99.4% |
| 有意差ゲート付きリーダーボード | `evaluation/leaderboard.py` | champion=null を表現可能に |
| コンフォーマル予測 + ACI | `evaluation/conformal.py` | 分布仮定なしの有限標本被覆保証 |
| リーク負対照 | `evaluation/sentinel.py` | リークを反証可能にする |
| 階層整合化 | `reconciliation/hierarchy.py` | total→parity→decade→number の coherence |
| 意識的選択回避 | `strategy/popularity.py` | 8サイクルPDCAで唯一実効だった戦略 |
| 間欠需要モデル | catalog (Croston/ADIDA/IMAPA/TSB) | 各数字の出現は構造的に間欠系列 |
| 全ゲーム厳密理論限界 | `evaluation/theory_general.py` | MAE下限/MSE下限/±1上限を別々に提示 |

## v3 モジュールのカバレッジ

| module | stmt | coverage |
|---|---:|---:|
| `calibration/calibrators` | 40 | 100.0% |
| `cli_v3` | 127 | 98.4% |
| `contracts_general` | 39 | 97.4% |
| `data/provenance` | 55 | 90.9% |
| `data/robots` | 75 | 100.0% |
| `evaluation/conformal` | 100 | 90.0% |
| `evaluation/leaderboard` | 123 | 95.1% |
| `evaluation/metrics_general` | 150 | 84.7% |
| `evaluation/multiplicity` | 125 | 85.6% |
| `evaluation/pace_gate` | 30 | 100.0% |
| `evaluation/promotion` | 32 | 96.9% |
| `evaluation/protocol` | 75 | 92.0% |
| `evaluation/sentinel` | 68 | 94.1% |
| `evaluation/theory_general` | 95 | 98.9% |
| `game/geometry` | 106 | 82.1% |
| `models/catalog_full` | 98 | 98.0% |
| `orchestration/research_v3` | 263 | 88.6% |
| `reconciliation/hierarchy` | 106 | 90.6% |
| `strategy/popularity` | 136 | 94.9% |
| `verify/integrity` | 146 | 81.5% |

## 未認定（外部依存 / 長時間Run）

| 領域 | 状態 | 解除条件 |
|---|---|---|
| TSFM revision 固定 | 21 件 UNPINNED | ネットワーク環境で `loto3 catalog --unpinned` を解決 |
| live HTTP 取得 | 実装済み・未実行 | robots.txt 確認後に `loto data acquire` |
| neuralforecast 実学習 | 73 系 UNAVAILABLE | `uv sync --extra full` + RTX 5070 Ti |
| PostgreSQL | 境界実装済み | service 起動 + 実 COPY |
| MLflow / Ray / Grafana / Loki / Tempo | bridge 実装済み | server 起動 |
| Slack / SMTP | local JSONL のみ検証 | 実配送 |
| Holdout 開封・champion 昇格 | 未実施（設計上封印） | sentinel CLEAN + PACE ACCEPT + 明示的開封 |
| Ruff / mypy | `dev` に宣言済み | 本環境に未導入。未実行を PASS とはしない |

## 科学的立場

本プラットフォームは予測優位性を主張しません。i.i.d. な抽選に対し seasonal-naive を有意に
上回るモデルは 8 サイクルの PDCA で確認されていません。v3 の価値は「勝てない」ことを
**統計的に正しく検出できる装置**であることにあります。

`loto3 research` を i.i.d. 合成データで実行すると、6ゲーム全てで
`NO_MODEL_BEATS_BASELINE` / `champion: null` が返ります。これは失敗ではなく期待される出力です。
