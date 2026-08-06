# Loto Forecast Platform

6ゲーム（ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4）を対象に、統計・機械学習・
深層学習・時系列基盤モデルを **統計的に正当な手続きで** 比較する研究＋運用基盤です。

> 現在のpackage versionはREADMEへ手書きしません。`src/loto/version.py`を正本とし、
> `uv run loto --version`、`uv run loto3 --version`、またはpackage metadataで確認します。
> 以下のversion番号は過去releaseとの比較や履歴見出しです。

v2.1.0 の独立監査で検出された10件の構造的欠陥を修正し、spec-kit の SDD サイクル
（constitution → specify → plan → tasks → implement）で再構築しました。

- 仕様: [`specs/001-full-coverage/spec.md`](specs/001-full-coverage/spec.md)
- 計画・設計判断: [`specs/001-full-coverage/plan.md`](specs/001-full-coverage/plan.md)
- 一次情報調査ログ: [`specs/001-full-coverage/research.md`](specs/001-full-coverage/research.md)
- タスク: [`specs/001-full-coverage/tasks.md`](specs/001-full-coverage/tasks.md)
- 憲章: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)

## v2.1.0 との差分

| 項目 | v2.1.0 | v3.0.0 |
|---|---:|---:|
| 予測・評価できるゲーム | 1 (ロト7のみ) | **6** |
| 登録モデル | 84 | **174** |
| テスト | 53 | **313** |
| カバレッジ | 65% | **75%** |
| チェックサムマニフェスト | 2個（14/82不一致） | **1個（自己検証つき）** |
| テスト密封性 | optuna有無で判定が変化 | **環境非依存** |
| リーダーボードの分散情報 | なし | **n / sd / se / 区間 / 補正済みp** |
| 多重比較補正 | なし | **Holm / BH / Romano-Wolf** |
| 統計的受入層 | デッドコード | **研究ループへ結線** |
| リーク検出 | なし | **3種の負対照 + 厳密因果監査** |

## 5分で確認する

```bash
uv sync --extra dev
uv run pytest -q                      # 313 passed
uv run loto --version                 # package version
uv run loto3 games                    # 6ゲームの幾何
uv run loto3 theory --game loto7      # 厳密理論限界（MAE下限 3.8337）
uv run loto3 catalog --counts         # モデル件数（計算値）
uv run loto3 integrity check          # 成果物の自己検証
uv run loto3 research --game numbers4 # v2.1.0で不可能だったゲームの研究実行
```

## 設計上の核心

### 1. ゲーム幾何の単一情報源

`loto.game.GameGeometry` が universe / slot / family を一元管理します。`select` 族（重複なし・
昇順）と `digits` 族（重複可・先頭0有意）を別物として扱うため、ナンバーズの指標が黙って
壊れることがありません。`loto.game` の外に幾何リテラルが現れないことを AST ベースのテストで
強制しています。

### 2. protocol_hash

評価条件22項目の SHA-256。モデル実行より**先に**確定し、異なる hash 同士の比較は
`ProtocolMismatch` で実行時に拒否されます。hash 欠落は「不明な protocol」として扱い、
黙って一致とみなしません。

### 3. champion は null になりうる

`Leaderboard.champion` の型は `LeaderboardRow | None` です。多重比較補正後にベースラインを
有意に上回るモデルがなければ `verdict = NO_MODEL_BEATS_BASELINE` / `champion = null` を返します。
i.i.d. な抽選に対してこれが**正解**であり、v2.1.0 がこれを表現できなかったことが
「Champion: uniform」の原因でした。

さらに `composite_score` は sharpness 項を伴わない `ece` 重み付けを拒否します。定数予測は
`ece = 0` を構造的に達成するため、校正のみを評価する目的関数は自明なモデルを優遇します。

### 4. リークは反証可能

毎回の研究実行でラベル置換・時間シフト・厳密因果監査を実施します。どれかが偶然水準を
上回れば `SENTINEL_TRIPPED` となり昇格が阻止されます。全て通過した場合の解釈文は
「absence of evidence only」であり、リークがないとは主張しません。

### 5. 意識的選択回避

パリミュチュエルのため期待値は「不変の当選確率 × 改善可能な共同当選者数」に分解できます。
実績当選口数から log 線形の人気度曲面を推定しますが、**置換検定で有意でなければ提案を返しません**。
当選確率は全ての正当な組合せで同一であり「改善不可能」と明示します。

## モデル在庫

件数は `loto3 catalog --counts` が唯一の正です（[`docs/MODEL_INVENTORY.md`](docs/MODEL_INVENTORY.md)）。

| library | 件数 |
|---|---:|
| statsforecast | 41 |
| neuralforecast | 37 |
| neuralforecast_auto | 36 |
| tsfm | 21 |
| hierarchicalforecast | 10 |
| mlforecast_auto | 8 |
| sklearn / builtin / GBDT / framework | 21 |
| **合計** | **174** |

TSFM 21 件は `revision` 未固定（`UNPINNED`）です。未確認のコミットSHAは
**捏造しません**。protocol_hash の再現性を偽ることになるためです。`loto3 catalog --unpinned` で列挙できます。

### DBからNeuralForecast AutoModelを実行

SQLiteまたはPostgreSQLのテーブルを読み込み、Numbers4の`d1`～`d4`を4系列へ変換して、
登録済み36 AutoModelを一括実行できます。最初にdry-runでDBスキーマと実行計画を確認してください。

```bash
uv run loto neuralforecast automodel-run \
  --db-url /absolute/path/to/datasets.sqlite3 \
  --table normalized_draws \
  --game numbers4 \
  --output runs/numbers4-nf-auto \
  --models all \
  --backend optuna \
  --workers 8 \
  --gpus 1 \
  --max-gpu-jobs 1 \
  --dry-run
```

実学習、smoke設定、AutoHINTのRay専用処理、成果物構成は
[`docs/NEURALFORECAST_DB_AUTOMODEL.md`](docs/NEURALFORECAST_DB_AUTOMODEL.md)を参照してください。

## 理論限界

[`docs/THEORETICAL_BOUNDS.md`](docs/THEORETICAL_BOUNDS.md)（`loto3 theory` で再生成）。
順序統計量 pmf を `fractions.Fraction` で厳密計算しています。ロト7の MAE 下限 3.8337 と
全ゲームの全事象数が公表当選確率と一致することが、幾何表の独立検証になっています。

**MAE 下限と ±1 上限は同時達成できません。** ±1 最適予測の MAE は下限より悪く（ロト7: 4.0185 対
3.8337）、中央値予測の ±1 率は上限より低い（0.2429 対 0.2923）。全 select ゲームでテスト強制しています。

## 未認定事項

隠さず記載します。いずれも v2.1.0 でも未認定であり、後退ではありません。

- TSFM 21 件の `revision` 未固定
- loto-life.net への live HTTP 取得（robots.txt 対応実装済み・未実行）
- RTX 5070 Ti 上での neuralforecast 73 系の実学習
- PostgreSQL / MLflow server / Ray / Grafana / Loki / Tempo / Slack / SMTP
- Holdout の開封と正式な champion 昇格
- Ruff / mypy（`dev` に宣言済み・本環境に未導入）

詳細は [`docs/IMPLEMENTATION_STATUS_V3.md`](docs/IMPLEMENTATION_STATUS_V3.md)。

## ライセンスと免責

本ソフトウェアは時系列予測手法の**研究**を目的とします。宝くじの当選を予測する能力は
主張しません。8サイクルの PDCA バックテストで、i.i.d. な抽選に対し seasonal-naive を
有意に上回るモデルは存在しないことが確認されています。実装されている唯一の実効戦略は
配当分散の回避であり、当選確率を変えるものではありません。

## v3.2.0: All-model / all-setting bounded auto coverage research

Run data acquisition and the bounded, resumable search for Mini Loto, Loto6 and Loto7:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_auto_coverage_loop.ps1 -AcquireData
```

The search enumerates every value explicitly listed in `parameter_spaces`, tests declared ensembles,
selects the smallest candidate set it can find for the requested ±1 row coverage, and optionally asks
an OpenAI-compatible local LLM for additional bounded proposals every N experiments. It never opens the
protected test during tuning and never reports 90% unless validation actually reaches it.

Important: "all settings" cannot mean every real-number value or every possible neural architecture.
Here it means the complete finite Cartesian product declared in the YAML. Expand that YAML intentionally,
subject to `max_experiments` and `max_runtime_seconds`.
