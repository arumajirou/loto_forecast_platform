# Loto Forecast Platform

現在のpackage versionはREADMEへ手書きしません。canonical versionは`loto.version.__version__`、installed CLI、またはpackage metadataから確認してください。

6ゲーム（ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4）を対象に、統計・機械学習・深層学習・時系列基盤モデルを **統計的に正当な手続きで** 比較する研究＋運用基盤です。

## Current execution status — 2026-08-10

この節は「リポジトリが対応しうる全OS」ではなく、**現在このプロジェクトで実際に操作・検証できる実行環境**を記録します。

```text
CURRENT_OPERATOR_EXECUTION_ENVIRONMENT=native Windows only
LINUX_EXECUTION_CURRENTLY_AVAILABLE=false
WSL_EXECUTION_CURRENTLY_AVAILABLE=false
PR_240_STATE=open/draft
LAST_CODE_BEARING_PR_HEAD=7795c413d295f445dbdcdf8d85894bf6c81db35a
FORMAL_OOF_RUN=false
TIMER_INFERENCE_RUN=false
HOLDOUT_OPENED=false
PROSPECTIVE_OPENED=false
```

現在のnative Windows self-hosted GitHub Actions runnerは次の状態まで検証済みです。

```text
runner_name=az-loto-windows
runner_version=2.336.0
runner_service=Running
runner_service_account=NT AUTHORITY\NETWORK SERVICE
PowerShell=7.6.4
windows_portability_run=31353996850
windows_portability_latest_job=93356157095
windows_portability_result=SUCCESS
windows_portability_steps=13/13 success
```

Windows portability CIでは、runner identity、checkout、exact uv、managed Python、committed universal lock、native Windows dependency resolution、Triton非選択、wheel build、wheel install/import、tracked-files-cleanまでPASSしています。

一方、**正式なTimer Base 84M OOF実行はまだ開始していません**。次工程はWindows上での`EvaluationProtocolV2`最終固定です。過去のLinux上のprotocol fixation evidenceは履歴として保持しますが、現在Linuxを実行できないため、そのresource identityを新しい正式runへコピーしてはいけません。Windows上でcode/data/resource/package identityを再測定してから新しいprotocol hashを固定します。

詳細:

- [`docs/WINDOWS_INSTALL.md`](docs/WINDOWS_INSTALL.md)
- [`docs/windows_only_execution/README.md`](docs/windows_only_execution/README.md)
- [`docs/windows_only_execution/RUNBOOK.md`](docs/windows_only_execution/RUNBOOK.md)
- [`docs/windows_only_execution/HANDOFF.md`](docs/windows_only_execution/HANDOFF.md)

## Scientific acceptance policy

最優先指標は`Hit@±1`です。併記する指標は`MAE`、`MSE`、`RMSE`、位置別`Hit@±1`、全位置`Hit@±1`です。formal比較では最低限、Random、固定値、平均、中央値、直近値、頻度、統計モデルを同一protocolで比較します。

Train / Validation / Holdout / Prospectiveは時間順で分離し、Scaler、Encoder、特徴量選択、HPOはTrain内だけで行います。OOFは複数seedの平均・分散・最悪値を保存し、最良seedだけでは採用しません。予測値は実測参照前にSHA-256と時刻で固定します。

## Repository design sources

v2.1.0 の独立監査で検出された構造的欠陥を修正し、spec-kit の SDD サイクル（constitution → specify → plan → tasks → implement）で再構築しました。

- 仕様: [`specs/001-full-coverage/spec.md`](specs/001-full-coverage/spec.md)
- 計画・設計判断: [`specs/001-full-coverage/plan.md`](specs/001-full-coverage/plan.md)
- 一次情報調査ログ: [`specs/001-full-coverage/research.md`](specs/001-full-coverage/research.md)
- タスク: [`specs/001-full-coverage/tasks.md`](specs/001-full-coverage/tasks.md)
- 憲章: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)

## 5分で確認する — current Windows path

現在の操作環境ではnative Windowsを標準とします。

```powershell
uv --version
uv sync --extra dev
uv run pytest -q
uv run loto3 games
uv run loto3 catalog --counts
uv run loto3 integrity check
```

Windows portabilityのdependency-light smokeは次で確認できます。

```powershell
uv python install 3.12.13
uv lock --check
uv sync --dry-run --locked --python 3.12.13
uv tree --locked --python-version 3.12 --python-platform x86_64-pc-windows-msvc
uv build --wheel
```

Linux/bash例が既存資料に残っている場合、それはplatform-specificな履歴または別ターゲット向け手順です。**現在のoperator execution pathとしてLinux/WSLを前提にしてはいけません。**

## 設計上の核心

### 1. ゲーム幾何の単一情報源

`loto.game.GameGeometry` が universe / slot / family を一元管理します。`select` 族（重複なし・昇順）と `digits` 族（重複可・先頭0有意）を別物として扱います。

### 2. protocol_hash

評価条件をSHA-256で固定し、異なるhash同士の比較を拒否します。現在のTimer Base 84M正式OOFでは、最終コードidentity・frozen development snapshot・Windows resource/package identityを固定した**新しい**`EvaluationProtocolV2` hashが必要です。

### 3. champion は null になりうる

`Leaderboard.champion` の型は `LeaderboardRow | None` です。多重比較補正後にベースラインを有意に上回るモデルがなければ `verdict = NO_MODEL_BEATS_BASELINE` / `champion = null` を返します。

### 4. リークは反証可能

研究実行ではラベル置換・時間シフト・厳密因果監査を実施します。Timer Base 84M OOF foundationでは、target contextを対象drawより前に限定し、prediction recordを実測参照前にimmutable write + SHA-256 sealします。

### 5. Runtime certificationはavailability表示と別物

モデルが利用可能と表示されるだけでは正式成功ではありません。load、input、inference、output shape、finite values、device、GPU PID/VRAM、CPU fallbackを実測して初めてruntime evidenceとします。

## モデル在庫

件数は `loto3 catalog --counts` が唯一の正です（[`docs/MODEL_INVENTORY.md`](docs/MODEL_INVENTORY.md)）。README上の古い件数は参考値であり、実行時inventoryを優先してください。

## DBからNeuralForecast AutoModelを実行

SQLiteまたはPostgreSQLのテーブルを読み込み、Numbers4の`d1`～`d4`を4系列へ変換して登録済みAutoModelを実行できます。現在のoperator environmentではWindows PowerShell構文を優先してください。formal runの前にはdry-runでDBスキーマと実行計画を確認し、Holdout/Prospectiveを開かないことを確認します。

## 理論限界

[`docs/THEORETICAL_BOUNDS.md`](docs/THEORETICAL_BOUNDS.md)（`loto3 theory` で再生成）。MAE下限と±1上限は別目的であり、同時最適化できない場合があります。formal比較ではPrimary KPIをHit@±1として固定し、MAE/MSE/RMSEを併記します。

## Current certification boundary

現在の事実として確認済み:

- PR #240のcode-bearing head `7795c413d295f445dbdcdf8d85894bf6c81db35a`でWindows focused validation 20/20 PASS
- 同code-bearing headに対するLinux standard CIは過去にPASS済み。ただし現在Linuxを実行できないため**historical evidence**として扱う
- native Windows runner `az-loto-windows`復旧済み
- PowerShell 7.6.4導入済み
- Windows portability CI run `31353996850` / latest job `93356157095` = SUCCESS, 13/13 steps PASS
- Holdout actuals opened=false
- Prospective actuals opened=false
- formal OOF run=false
- Timer inference run=false

未完了または未認定:

- Windows上でのfinal `EvaluationProtocolV2`再固定
- frozen development snapshotのWindows側存在確認とSHA-256再検証
- Windows resource/package identityのformal protocolへの固定
- formal baseline OOF
- formal Timer Base 84M OOF
- 複数seedのmean / variance / worst集約
- Holdout開封とProspective評価
- champion / promotion

## ライセンスと免責

本ソフトウェアは時系列予測手法の**研究**を目的とします。宝くじの当選を予測する能力は主張しません。正式な性能主張は、固定済みprotocol、リーク検査、baseline比較、multi-seed集約、prediction sealingを通過したevidenceだけを根拠にします。

## v3.2.0: All-model / all-setting bounded auto coverage research

Native Windowsでは次のPowerShell entrypointを使用できます。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_auto_coverage_loop.ps1 -AcquireData
```

The search enumerates every value explicitly listed in `parameter_spaces`, tests declared ensembles, selects the smallest candidate set it can find for the requested ±1 row coverage, and optionally asks an OpenAI-compatible local LLM for additional bounded proposals every N experiments. It never opens the protected test during tuning and never reports 90% unless validation actually reaches it.

"all settings" means the complete finite Cartesian product declared in the YAML, not every real-number value or every possible neural architecture.