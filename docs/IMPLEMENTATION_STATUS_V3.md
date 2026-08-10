# Implementation Status v3.0.0

## 2026-08-10 current-project addendum

The original v3.0.0 verification below is retained as historical evidence. The current project execution boundary has materially advanced and must be read first.

```text
CURRENT_OPERATOR_EXECUTION_ENVIRONMENT=native Windows only
LINUX_EXECUTION_CURRENTLY_AVAILABLE=false
WSL_EXECUTION_CURRENTLY_AVAILABLE=false
PR_240_STATE=open/draft
LAST_CODE_BEARING_PR_HEAD=7795c413d295f445dbdcdf8d85894bf6c81db35a
ENGINEERING_IMPLEMENTATION_CI_GATES=7/7 PASS
SCIENTIFIC_PROGRESS=18%
FORMAL_OOF_RUN=false
TIMER_INFERENCE_RUN=false
HOLDOUT_OPENED=false
PROSPECTIVE_OPENED=false
```

### Newly verified since the original report

| Area | Current verified state | Evidence identity |
|---|---|---|
| PR #240 Windows focused validation | PASS | 20/20 focused tests + Ruff + mypy + py_compile + compileall smoke on code-bearing head |
| Linux standard CI | PASS, historical environment evidence | run `31353996862` on code-bearing head `7795c413...` |
| Native Windows self-hosted runner | PASS | `az-loto-windows`, runner v2.336.0, Windows X64, service Running |
| PowerShell runtime for Actions | PASS | PowerShell 7.6.4 machine-wide |
| Windows portability CI | PASS | run `31353996850`, latest job `93356157095`, 13/13 steps success |
| Native Windows lock/dependency resolution | PASS | committed universal lock checked; Windows dependency tree excludes Triton |
| Native Windows package smoke | PASS | wheel build + `--no-deps` install + `import loto` |
| Formal Timer Base 84M OOF | NOT STARTED | protocol rehash/fixation still required |

### Current execution policy

The repository may contain Linux-specific historical evidence and Linux-targeted adapters, but the **current operator can execute only native Windows**. Therefore:

- do not instruct the current operator to run Linux/WSL-only commands as the next required step;
- do not copy historical Linux resource/package values into a new formal protocol;
- regenerate formal protocol identities from Windows when the frozen development snapshot is available and verified;
- preserve historical Linux artifacts unchanged;
- keep Holdout and Prospective closed;
- treat documentation-only commits after `7795c413...` separately from the last code-bearing identity and rerun required CI on the final documentation head.

### Current scientific gate

Engineering implementation and portability infrastructure are ready, but scientific acceptance is not. Before any formal accuracy claim, the project still requires:

1. frozen development snapshot availability on Windows;
2. exact SHA-256 verification of that snapshot;
3. final Windows-native `EvaluationProtocolV2` fixation;
4. 5-game × 2-layout protocol artifact generation;
5. baseline OOF;
6. Timer Base 84M OOF;
7. all-seed mean/variance/worst aggregation;
8. Hit@±1-first reporting with MAE/MSE/RMSE, position Hit@±1 and all-position Hit@±1;
9. explicit non-opening of Holdout and Prospective until later gates.

---

判定日: 2026-07-30 / 総合判定: **VERIFIED (light environment)** + **NOT_CERTIFIED (external deps)**

軽量環境（numpy / pandas / pydantic / scikit-learn / scipy / PyYAML / prometheus-client / fastapi / pytest / optuna）で実行可能な経路は当時の範囲で検証済みです。以下はその時点の履歴であり、上の2026-08-10 addendumを上書きしません。

## Historical verified values from 2026-07-30

| 指標 | 値 | 取得方法 |
|---|---:|---|
| pytest | **313 passed / 0 failed** | `pytest -q`（`--extra dev` のみ） |
| coverage | **75%** (3995/5328 stmt) | `pytest --cov=src/loto` |
| 登録モデル | **174** | `loto3 catalog --counts` |
| 対応ゲーム | **6 / 6** | `test_run_completes_for_every_game` |
| テスト密封性 | optuna 有無で判定同一 | uninstall → rerun で実証 |
| 完全性マニフェスト | 1個 / 自己検証つき | `loto3 integrity check` |

## v2.1.0 detected defects and responses

| # | 欠陥 | 対応 | 検証テスト |
|---|---|---|---|
| 1 | `verification/SHA256SUMS` が 14/82 FAILED（旧版残骸） | 削除。`INTEGRITY.json` に一本化し MODIFIED/MISSING/**UNTRACKED** を区別 | `test_added_file_is_reported_as_stale_manifest` |
| 2 | `except Exception` により optuna 有無でテスト判定が変化 | `ImportError` のみに限定し、欠落パッケージ名を出力。optuna を `dev` へ宣言 | `test_api_exposes_runs_events_resources_and_games` |
| 3 | pace_gate / promotion / calibrators / stacking がデッドコード | research 経路へ結線 | `test_pace_gate_is_wired_not_dead_code` |
| 4 | 予測・評価コアが 37/7 ハードコード | `GameGeometry` へ集約 | `test_no_hardcoded_geometry_outside_game_package` |
| 5 | 品質ゲートが来歴列の全NULLを PASS | `data/provenance.py` を追加 | `test_the_exact_v2_defect_is_caught` |
| 6 | 中核 `research.py` が低coverage | v3中核を新規実装 | focused coverage suite |
| 7 | モデル集計が不整合 | 件数を計算値化 | `test_library_subtotals_sum_to_total` |
| 8 | TSFM に repo/revision がなく再現不能 | `repo_id` 付与。未確認SHAは `UNPINNED` | `test_unpinned_revisions_are_flagged_not_fabricated` |
| 9 | stale `api/openapi.json` | 削除し単一化 | — |
| 10 | robots.txt / ToS 未確認 | `data/robots.py` | `test_disallowed_url_is_refused` |

## Current certification boundary

Still not certified merely from the Windows portability gate:

- every optional dependency group;
- every model/provider runtime on Windows;
- every CUDA model path on Windows;
- Ray/Optuna/provider-specific Windows runtime behavior;
- production deployment equivalence;
- Holdout or Prospective results;
- champion or promotion eligibility.

## Scientific position

本プラットフォームは予測優位性を主張しません。正式な性能主張は、固定済みprotocol、リーク検査、required baseline比較、multi-seed集約、prediction sealing、runtime evidenceが揃ったrunだけを根拠にします。現時点ではformal Timer Base 84M OOFは未実行です。