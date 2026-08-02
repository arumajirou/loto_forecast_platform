# Setup and execution

## Linux / WSL

```bash
unzip loto_ops_pipeline-fixed.zip
cd loto_ops_pipeline-fixed
bash setup_linux.sh
./run_loto_ops.sh --help
./run_loto_ops.sh run --dry-run
```

A normal operations run can then be started with a command such as:

```bash
./run_loto_ops.sh preflight
./run_loto_ops.sh run-all-fast --help
```

Database and scraper operations require the configured PostgreSQL service, external project paths, and credentials.

## Windows PowerShell

```powershell
Expand-Archive .\loto_ops_pipeline-fixed.zip -DestinationPath C:\Users\bp00425\env\ts
Set-Location C:\Users\bp00425\env\ts\loto_ops_pipeline-fixed
.\setup_windows.ps1
.\run_loto_ops.ps1 --help
.\run_loto_ops.ps1 run --dry-run
```

Native Windows supports CLI validation and Python-only commands. Commands that invoke Bash, systemd, WSL paths, or Linux-only external tools should be run under WSL.

## Configuration

The launchers set these variables automatically:

- `LOTO_OPS_PROJECT`
- `LOTO_OPS_CONFIG`
- `LOTO_OPS_RUNS_DIR`
- `LOTO_HANDOVER_DIR`
- `LOTO_SKILLS_DIR`

Set `DB_PASSWORD` and notification secrets through environment variables or a local ignored `configs/notify.env`; do not commit secrets.


## v2 runtime corrections

- Added `PipelineOrchestrator.preflight()` with safe `--auto-fix`.
- Replaced the obsolete raw `runs_dir` dependency with `settings.paths.runs_dir`.
- Added automatic discovery of sibling `/mnt/e/env/ts` projects when legacy `/mnt/e/env/fc` paths do not exist.
- Pipeline failures now produce non-zero CLI exit codes instead of a misleading empty success.

## Runtime order for v2

```bash
./run_loto_ops.sh preflight --auto-fix
./run_loto_ops.sh path-status
./run_loto_ops.sh run --dry-run
```

`preflight` returns `PARTIAL` rather than crashing when optional external data or database credentials are absent. Check `warnings`, `capabilities.database_configured`, and `ready_for_fast_pipeline`. When normalized input is missing, create it first:

```bash
./run_loto_ops.sh scrape --games all
./run_loto_ops.sh preflight
./run_loto_ops.sh run-all-fast --engine auto --mode light --unified-engine fast --package light
```

The scraper uses the auto-detected `loto_life_feature_pipeline`. Override explicitly when needed:

```bash
export LOTO_LIFE_PROJECT=/mnt/e/env/ts/loto_life_feature_pipeline
export LOTO_FORECAST_PROJECT=/mnt/e/env/ts/loto_neuralforecast_pipeline
export LOTO_ZIP_OUTPUT_DIR=/mnt/e/env/ts/zips
```

Configure PostgreSQL credentials through environment variables rather than committing secrets:

```bash
export DB_HOST=127.0.0.1
export DB_PORT=5432
export DB_USER=loto
export DB_PASSWORD=YOUR_PASSWORD
export DB_NAME=loto
```
