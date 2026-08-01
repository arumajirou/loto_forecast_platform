# 003 — KPI Lab: 有限で反証可能な被覆KPI探索

| 項目 | 値 |
|---|---|
| Feature | 003-kpi-lab |
| Status | IMPLEMENTED / VERIFIED |
| 前提 | 001-full-coverage、`.specify/memory/constitution.md` |
| 実装 | `src/loto/combinatorics/`、`src/loto/kpi_lab/` |
| CLI | `loto-lab` |

---

## 1. 背景と問題

`src/loto/coverage/auto_research.py` は既にKPI駆動の自律探索を実装している。

```python
class SearchBudget:
    max_candidates: int = 5000
    target_coverage: float = 0.90
    tolerance: int = 1
    stop_when_target_met: bool = True
```

この設計には3つの構造的欠陥がある。

### 1.1 KPIに分母がない

`row_within_tolerance >= 0.90` は「候補プール中の少なくとも1口が全位置±1以内」である。
口数の上限が `max_candidates` として可変なため、口数を増やせば必ず達成する。

`reports/kpi-feasibility.md` の計算より、パッキング下限は次の通り。

| ゲーム | 90%被覆の最小口数 | 購入費用 |
|---|---:|---:|
| ロト7 | 4,237 | ¥1,271,100 |
| ロト6 | 7,527 | ¥1,505,400 |
| ビンゴ5 | 10,550 | ¥2,110,000 |
| ミニロト | 630 | ¥126,000 |
| ナンバーズ4 | 112 | ¥22,400 |
| ナンバーズ3 | 34 | ¥6,800 |

この下限は**モデル独立**である。重複ゼロを仮定した容積限界であり、いかなる予測手法も下回れない。
したがって「90%達成」は予算の報告であって性能の報告ではない。

### 1.2 早期停止が選択バイアスを最大化する

`stop_when_target_met=True` は閾値を最初に超えた実験で停止する。500試行に対する最大値選択を
単一測定として報告する手続きであり、名目閾値が誤り率を制御しなくなる。報告される勝者は
運が良かった実験であり、これがホールドアウトで崩壊する機序そのものである。

### 1.3 一様i.i.d.下では予測問題ではない

抽選が一様i.i.d.であれば全事象は等確率であり、プールが最適化できるのは幾何的パッキングのみである。
これは被覆符号の構成問題であり、履歴データを一切使わない。時系列基盤モデルの寄与は原理的にゼロ。

## 2. 目的

**KPI達成ではなく、KPI達成の可否と意味を証拠付きで決着させ、必ず有限時間で停止すること。**

「モデルに価値がない」という結論は、「価値がある」と同等に価値のある成果である。

## 3. 機能要件

| ID | 要件 | 実装 |
|---|---|---|
| FR-LAB-001 | 実装・探索の前にパッキング下限を計算し、予算未達ならモデルを一切走らせず終了する | `bounds.feasibility_bound` / `state_machine` FEASIBILITY_GATE |
| FR-LAB-002 | KPIは口数を固定した費用正規化指標として定義する。`n_tickets` は必須かつ不変 | `kpi.KpiDefinition` |
| FR-LAB-003 | `efficiency > 1.0`（下限超過）を例外として拒否する | `kpi.KpiMeasurement.__post_init__` |
| FR-LAB-004 | データ非依存の参照腕（Arm A）を先に完走させ、これなしにArm Bの結果を出力しない | `arms.build_reference_arm` / BASELINE_ARM_A |
| FR-LAB-005 | 同一口数・同一封印抽選での対比較を唯一の判定軸とする | `arms.compare_arms`、`ArmComparison.equal_ticket_count` |
| FR-LAB-006 | 早期停止をanytime-valid e-processへ置換する | `stopping.EProcess` |
| FR-LAB-007 | 負のコントロールを探索ループ内で毎反復実行する | `negative_controls.run_control_suite` |
| FR-LAB-008 | 陽性対照（未来情報注入）が発火しない場合、負のコントロール通過を無効とする | `ControlSuiteReport.has_demonstrated_power` |
| FR-LAB-009 | 偽陽性率が上限を超えたらラボを自動停止する。閾値を実行中に緩めない | `LEAK_DETECTED_SUSPENDED` |
| FR-LAB-010 | LLM提案を非信頼データとして扱う。スキーマ検証・許可リスト・範囲クランプ | `proposer.validate_proposal` |
| FR-LAB-011 | LLM不通時はsilent fallbackせず、型付きstatusとログを残す | `ProposerResult.status == "UNAVAILABLE"` |
| FR-LAB-012 | 全実験を改竄検知付き台帳に記録する。閾値超過後も記録を止めない | `ledger.ExperimentLedger` |
| FR-LAB-013 | 封印窓は構造的に保護し、探索中の参照を例外にする | `state_machine._SealedWindow` |
| FR-LAB-014 | 被覆率から期待収益を導出しない | `kpi.CostModel` |
| FR-LAB-015 | 一様乱数データで必ず否定的終端状態に到達する | AC-LAB-003 |

## 4. 非機能要件

| ID | 要件 |
|---|---|
| NFR-REP-001 | 全数値は計算由来とし、ドキュメントへの手打ちを禁止（憲章I） |
| NFR-REP-002 | e-process状態は直列化可能で、中断・再開が同一継続を与える |
| NFR-SEC-001 | LLM出力から `eval`/`exec`/`import`/パス解決への経路を持たない |
| NFR-STAT-001 | 全報告に n・信頼区間・e-value・`kpi_definition_hash` を併記（憲章V） |
| NFR-OBS-001 | Prometheusラベルは閉集合のみ。session/experiment IDをラベルにしない |
| NFR-DEP-001 | OR-Tools は任意依存。不在時は `SolverUnavailable` を送出し貪欲へ暗黙降格しない（憲章II） |
| NFR-GAME-001 | ゲーム形状は `GameGeometry` からのみ取得。ハードコード禁止（憲章IV） |

## 5. KPI定義

```text
KPI-1  coverage_efficiency = L_lower(achieved_coverage) / n_tickets
       1.0 がパッキング下限。>1.0 は不可能であり欠陥かリークを意味する。

KPI-2  arm_delta = coverage(Arm B) - coverage(Arm A)
       同一口数・同一封印抽選での対比較。<= 0 ならモデルの寄与なし。

KPI-3  期待収支は完全一致確率からのみ算出し、被覆率から導出しない。
KPI-4  負のコントロール偽陽性率 <= max_false_positive_rate（既定0.05）
KPI-5  e-value >= 1/alpha（既定alpha=0.01 → 100）でのみモデル勝利を宣言
KPI-6  kpi_definition_hash 一致（異なるhash間の比較は不可）
```

## 6. 状態機械

```text
INIT → FEASIBILITY_GATE → PROTOCOL_FREEZE → BASELINE_ARM_A
     → NEGATIVE_CONTROL_CALIB → SEARCH_LOOP → CONFIRMATION → TERMINAL
```

終端状態:

| 状態 | 意味 | 成功扱い | 終了コード |
|---|---|---|---|
| `KPI_INFEASIBLE` | 予算 < パッキング下限。モデルを走らせずに終了 | ○ | 3 |
| `KPI_MET_DEGENERATE` | 達成したが予算のみで説明できる。KPI定義の欠陥として報告 | ○ | 0 |
| `KPI_MET_NO_MODEL_VALUE` | 達成したがArm Aと有意差なし。被覆構成が効いた | ○ | 0 |
| `KPI_MET_VERIFIED` | Arm Aを有意に上回り全コントロール通過。唯一モデル性能を主張できる | ○ | 0 |
| `BUDGET_EXHAUSTED` | 予算内で決着せず。到達した上界を報告 | ○ | 0 |
| `LEAK_DETECTED_SUSPENDED` | 偽陽性率超過または陽性対照不発 | × | 4 |
| `PROTOCOL_VIOLATION` | hash不一致または封印窓の不正参照 | × | 5 |

5つの成功終端のうち**4つが否定的結果**である。`KPI_MET_VERIFIED` のみを成功とみなす設計は、
試行を重ねれば必ずノイズで停止するため採用しない。

## 7. Arm A の構成（実測ランキング）

loto7 / tolerance=1 / 2000口 / MC 4000-6000サンプルでの実測。

| 構成 | 被覆率 | 効率 |
|---|---:|---:|
| `offset_lattice` | 0.3118 | 0.734 |
| `greedy_uniform` | 0.2667 | 0.628 |
| `multiplicity_augmented` | 0.2072 | 0.488 |
| `random_legal` | 0.1945 | 0.458 |

2件は否定的結果であり、隠さず記録している。

- `multiplicity_augmented` はランダム以下。隣接値クラスタに予算を割く価値が事象空間の
  占有率に見合わない。
- `greedy_uniform` は `n_targets` が `n_tickets` と同程度だと自身のMCサンプルへ過適合する。
  抽選に対して過適合不可能であることは、自分のサンプルに対して過適合しないことを意味しない。

既定は実測最良の `offset_lattice`。

## 8. 明示的な非目標

- 当せん確率の改善を主張しない
- 単一スコアへの統合を行わない（MAE / 被覆率 / 費用は目的が異なる）
- `tolerance >= 1` の被覆を配当条件として扱わない

## 9. 既存実装との関係

`src/loto/coverage/` は削除していない。段階移行の対象であり、次の対応関係を持つ。

| 既存 | 後継 | 状態 |
|---|---|---|
| `coverage.core._coverage_mask` | `combinatorics.set_cover.coverage_mask` | 同等 |
| `coverage.core.greedy_coverage_select` | `combinatorics.set_cover.greedy_max_coverage` | 予算固定形へ変更 |
| `coverage.auto_research.SearchBudget` | `kpi_lab.kpi.KpiDefinition` + `state_machine.SearchBudget` | KPIと予算を分離 |
| `coverage.auto_research.LLMProposer` | `kpi_lab.proposer.LlmProposer` | スキーマ検証を追加 |
| `coverage.auto_research.run_auto_research` | `kpi_lab.state_machine.KpiLab.run` | 終端状態を追加 |
| （なし） | `combinatorics.bounds` | 新規。下限計算 |
| （なし） | `combinatorics.designs` | 新規。Arm A |
| （なし） | `kpi_lab.stopping` | 新規。e-process |

`evaluation/multiplicity.py` は既存実装が存在するが `coverage/auto_research.py` から
呼ばれていない。本featureは逐次検定（e-process）を採用したため直接依存はしないが、
複数ゲーム・複数KPI横断のランキングを出す段階では `multiplicity.correct` の接続が必要である
（憲章V）。未接続のままである点を既知の欠落として記録する。
