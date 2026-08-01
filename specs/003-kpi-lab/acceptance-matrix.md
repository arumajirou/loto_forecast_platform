# 003-kpi-lab Acceptance Matrix

| AC ID | 要件ID | 条件 | Test ID | 状態 |
|---|---|---|---|---|
| AC-LAB-001 | FR-LAB-001 | Feasibility Gate を通らずに探索が始まらない | `test_infeasible_gate_stops_before_search` | IMPLEMENTED |
| AC-LAB-002 | FR-LAB-004 | Arm A 未完走で Arm B の結果を出力しない | `test_states_visit_baseline_before_search` | IMPLEMENTED |
| AC-LAB-003 | FR-LAB-015 | 一様乱数データで否定的終端状態に到達する | `test_uniform_noise_yields_no_model_value` | IMPLEMENTED |
| AC-LAB-004 | FR-LAB-008 | 陽性対照でコントロールスイートの検出力が確認される | `test_positive_control_fires` | IMPLEMENTED |
| AC-LAB-005 | FR-LAB-009 | 偽陽性率超過で `LEAK_DETECTED_SUSPENDED` | `test_impossible_improvement_suspends_lab` | IMPLEMENTED |
| AC-LAB-006 | NFR-REP-002 | e-process の中断→再開が同一継続を与える | `test_eprocess_restore_roundtrip` | IMPLEMENTED |
| AC-LAB-007 | FR-LAB-006 | e-value が 1/alpha を超えるまで勝利宣言しない | `test_eprocess_does_not_reject_under_null` | IMPLEMENTED |
| AC-LAB-008 | FR-LAB-013 | 封印窓の探索中参照が例外になる | `test_sealed_window_require_unopened` | IMPLEMENTED |
| AC-LAB-009 | NFR-STAT-001 | 全測定に n / CI / e-value / kpi hash が含まれる | `test_measurement_carries_statistics` | IMPLEMENTED |
| AC-LAB-010 | FR-LAB-014 | 被覆率から期待収益を導出しない | `test_cost_model_refuses_coverage_return` | IMPLEMENTED |
| AC-LAB-011 | FR-LAB-011 | LLM不通時に silent fallback せず typed status | `test_llm_unavailable_is_typed` | IMPLEMENTED |
| AC-LAB-012 | FR-LAB-010 | スキーマ外・範囲外の提案を拒否する | `test_proposal_rejects_unknown_keys`, `test_proposal_clamps_range_and_records_it` | IMPLEMENTED |
| AC-LAB-013 | FR-LAB-012 | 全実験が台帳に記録され、改竄が検出される | `test_ledger_detects_tampering` | IMPLEMENTED |
| AC-LAB-014 | FR-LAB-003 | 下限超過効率が例外になる | `test_efficiency_above_bound_raises` | IMPLEMENTED |
| AC-LAB-015 | NFR-DEP-001 | OR-Tools 不在時に暗黙降格しない | `test_cpsat_missing_backend_fails_closed`, `test_cpsat_installed_backend_returns_cpsat_result` | IMPLEMENTED |
| AC-LAB-016 | NFR-GAME-001 | 全6ゲームで下限が計算できる | `test_bounds_for_all_games` | IMPLEMENTED |

## 状態の意味

- `IMPLEMENTED` — コードとテストが存在し、対象環境で実行済み。
- `NOT_IMPLEMENTED` — 実装なし。理由を明記。

## 未実装の理由

**AC-LAB-015**: OR-Tools importをテスト内で遮断し、typed `SolverUnavailable` が送出され、
greedyへ暗黙降格しないことを全環境で検証する。OR-Tools導入済み環境では追加の条件付きテストが
実CP-SAT結果のmethodを検証する。依存追加自体は本バッチでは行わない。
