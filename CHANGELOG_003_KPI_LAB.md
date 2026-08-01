# 003-kpi-lab 追加改修サマリ

対象: `loto_forecast_platform` v3.2.0
実施日: 2026-07-30
状態: **IMPLEMENTED / VERIFIED（本サンドボックス環境）**

---

## 検証結果

```text
KPI Lab検証  PASS（pytest / ruff / compileall）
全回帰テスト  PASS（1 skipped、失敗なし）
ruff          All checks passed
契約スキーマ  8/8 実出力が Draft 2020-12 で検証通過
CLI          loto-lab bounds / run / verify を実行確認
台帳         chain intact (21 entries)
```

一様乱数（信号ゼロ）データでの終端状態:

```text
terminal_state : KPI_MET_NO_MODEL_VALUE
arm_delta      : -0.5287
e_value        : 0.0942  (閾値 100)
偽陽性率        : 0.0     陽性対照: PASS
claims skill   : False
exit code      : 0
```

---

## 追加した理由

`src/loto/coverage/auto_research.py` の既存KPIループには3つの構造的欠陥があった。

1. **KPIに分母がない。** `row_within_tolerance >= 0.90` は `max_candidates` を増やせば必ず達成する。
2. **`stop_when_target_met=True` が選択バイアスを最大化する。** 500試行の最大値を単一測定として報告する手続き。
3. **一様i.i.d.下では予測問題ではない。** 最適プールは被覆符号の構成問題であり、モデルの寄与は原理的にゼロ。

計算した下限（`loto-lab bounds`、全数値は計算由来）:

| ゲーム | 全事象数 | 1口最大被覆 | 90%被覆の最小口数 | 購入費用 |
|---|---:|---:|---:|---:|
| ロト7 | 10,295,472 | 2,187 | 4,237 | ¥1,271,100 |
| ロト6 | 6,096,454 | 729 | 7,527 | ¥1,505,400 |
| ビンゴ5 | 76,904,685 | 6,561 | 10,550 | ¥2,110,000 |
| ミニロト | 169,911 | 243 | 630 | ¥126,000 |
| ナンバーズ4 | 10,000 | 81 | 112 | ¥22,400 |
| ナンバーズ3 | 1,000 | 27 | 34 | ¥6,800 |

パッキング下限（重複ゼロ仮定）でありモデル独立。実際の必要口数はこれを上回る。

---

## 新規モジュール

### `src/loto/combinatorics/` — Arm A の理論基盤

| ファイル | 責務 |
|---|---|
| `bounds.py` | パッキング下限。1口被覆数は厳密DP（素朴な `3^n` は昇順制約を無視して過大評価するため不使用） |
| `designs.py` | データ非依存の被覆構成4種 + 実測ランキング |
| `set_cover.py` | 貪欲（予算固定形、(1−1/e)保証）/ LP双対下限 / CP-SAT任意経路 |
| `estimate.py` | 一様分布下モンテカルロ被覆推定。**抽選データを使わないため過適合が原理的に不可能** |

### `src/loto/kpi_lab/` — 状態機械

| ファイル | 責務 |
|---|---|
| `kpi.py` | 口数を必須固定にしたKPI定義。`CostModel` は被覆率から期待収益を導出しない |
| `arms.py` | Arm A（参照）/ Arm B（モデル）と対比較 |
| `stopping.py` | anytime-valid e-process（Ville不等式）。`stop_when_target_met` の置換 |
| `negative_controls.py` | 負性5種 + 陽性1種。探索ループ内で毎反復実行 |
| `proposer.py` | グリッド + 堅牢化LLM提案器。LLM出力は非信頼データ |
| `ledger.py` | SHA-256チェーン付き追記専用台帳 |
| `state_machine.py` | 終端7状態。`_SealedWindow` でホールドアウトを構造保護 |
| `metrics.py` | Prometheus。ラベルは閉集合のみ |
| `runner.py` / `cli.py` | 設定ロードと `loto-lab` CLI |

### 終端状態

| 状態 | 意味 | 成功 | exit |
|---|---|---|---|
| `KPI_INFEASIBLE` | 予算 < 下限。モデルを走らせず終了 | ○ | 3 |
| `KPI_MET_DEGENERATE` | 達成したが予算のみで説明可能 | ○ | 0 |
| `KPI_MET_NO_MODEL_VALUE` | 達成したがArm Aと有意差なし | ○ | 0 |
| `KPI_MET_VERIFIED` | Arm Aを有意に上回り全対照通過 | ○ | 0 |
| `BUDGET_EXHAUSTED` | 予算内で決着せず | ○ | 0 |
| `LEAK_DETECTED_SUSPENDED` | 偽陽性率超過または陽性対照不発 | × | 4 |
| `PROTOCOL_VIOLATION` | hash不一致/封印窓の不正参照 | × | 5 |

成功5状態のうち**4つが否定的結果**。`KPI_MET_VERIFIED` のみを成功とする設計は、
試行を重ねれば必ずノイズで停止するため採用しなかった。

---

## 実装中に発見・修正した自身の欠陥

いずれもテストを緩めず実装を修正した。

### 1. 計測前に効率0.79と記述（憲章I違反）

`greedy_uniform` の docstring に未計測の期待値を書いていた。実測は0.628で、
`offset_lattice`（0.734）より劣る。実測値へ訂正し既定構成を変更。

loto7 / tolerance=1 / 2000口 / MC実測:

| 構成 | 被覆率 | 効率 |
|---|---:|---:|
| `offset_lattice` | 0.3118 | 0.734 |
| `greedy_uniform` | 0.2667 | 0.628 |
| `multiplicity_augmented` | 0.2072 | 0.488 |
| `random_legal` | 0.1945 | 0.458 |

2件は否定的結果として保持している。`multiplicity_augmented` はランダム以下。
`greedy_uniform` は `n_targets` が `n_tickets` と同程度だと自身のMCサンプルへ過適合する
（抽選に対して過適合不可能であることは、自分のサンプルに対して過適合しないことを意味しない）。

### 2. コントロールハーネス自体がリークしていた

初版は偽陽性率0.6で全負性対照が発火。原因はモデルではなく、ハーネスの
`model_pool_builder` が採点対象の抽選に貪欲適合していたこと。ビルド窓と採点窓を
分離し、ビルダーには接頭辞のみを渡す形に修正。
`test_builder_cannot_see_scored_rows` で固定した。

### 3. 偽陽性率5%を主張しながら実際は約50%だった

`improvement_threshold=0.02` は n≈48 抽選でのサンプリングSD（≈0.07）を大きく下回るため、
固定デルタ判定では帰無仮説下でも約半数が発火する。「発火回数を0.05と比較する」ことに
統計的意味がなかった。対応McNemar型e-value（`>= 1/alpha`）と最小効果量の**両方**を
要求する形へ置換。

派生して、固定λ=0.1のベットが保守的すぎ29ペア全一致で E≈17（閾値100未満）にしか
ならず陽性対照が不発だったため、適応ベット（predictable plug-in）へ変更。
λ は過去の観測のみから決まるため予測可能性が保たれ、妥当性に影響しない。

### 4. `cli.py` の書き損じと契約スキーマのドリフト

`controls` サブコマンドに壊れた代入があった。また統計判定への変更で
`ControlResult` に追加したフィールドが `negative-control.schema.json` に未反映だった。
実出力をスキーマ検証にかけて発見。両方修正済み。

---

## 既存実装との関係

`src/loto/coverage/` は削除していない。段階移行の対象。対応表は
`specs/003-kpi-lab/spec.md` §9 を参照。

---

## 既知の未対応事項

| 項目 | 重大度 | 内容 |
|---|---|---|
| `evaluation/multiplicity.py` 未接続 | HIGH | 実装は存在するが `coverage/auto_research.py` から呼ばれていない。本featureは逐次検定を採用したため直接依存しないが、複数ゲーム・複数KPI横断のランキングを出す段階では憲章Vにより接続が必要 |
| `orchestration/research.py` と `research_v3.py` の重複 | MEDIUM | 21〜23KBの2実装が併存。どちらが正本か未確認 |
| `models/catalog.py` と `catalog_full.py` の重複 | MEDIUM | 同上。憲章Iは単一の機械可読catalogを要求 |
| AC-LAB-015（OR-Tools不在時の非降格） | LOW | `SolverUnavailable` は実装済みだが、ortools有無の両環境でのテストは未実装。憲章IIIによりortoolsをdev依存にするか `skipif` 明示が必要で、依存追加は承認事項のため保留 |
| 単価・当せん金体系 | INFO | `DEFAULT_UNIT_PRICE_JPY` は UNVERIFIED。一次情報での確認が必要 |
| bingo5 の被覆意味論 | INFO | select 8/40 として扱っているが、実際は5x5グリッドのライン判定。`GameGeometry` の既存定義を踏襲しているが他ゲームと同一意味かは未検証 |

## 明示的な非目標

- 当せん確率の改善を主張しない
- 被覆率と費用を単一スコアへ統合しない
- `tolerance >= 1` の被覆を配当条件として扱わない（日本の数字選択式宝くじで
  ±1に対する配当は存在せず、当せんには完全一致が必要。被覆率は予測精度の
  代理指標であって配当指標ではない）
