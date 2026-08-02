from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from loto_ops.artifacts.packager import ArtifactPackager
from loto_ops.config import load_settings
from loto_ops.db.admin import DbAdmin
from loto_ops.db.copy_loader import CopyLoader
from loto_ops.db.fast_copy_loader import FastCopyLoader
from loto_ops.notifications import NotificationSender, RunSummaryBuilder
from loto_ops.perf.exog_mode import ExogModeManager
from loto_ops.perf.resource_governor import ResourceGovernor
from loto_ops.pipeline.benchmark_runner import BenchmarkRunner
from loto_ops.pipeline.dataset_builder import DatasetBuilder
from loto_ops.pipeline.exog_runner import ExogRunner
from loto_ops.pipeline.fast_dataset_builder import FastDatasetBuilder
from loto_ops.pipeline.orchestrator import PipelineOrchestrator
from loto_ops.pipeline.scraper_runner import ScraperRunner
from loto_ops.pipeline.unified_fast_builder import UnifiedFastBuilder
from loto_ops.pipeline.unified_runner import UnifiedRunner
from loto_ops.progress import ProgressReporter, run_step
from loto_ops.quality.profiling import profile_important_tables
from loto_ops.quality.report import write_quality_reports
from loto_ops.scheduler.systemd_user import SystemdUserScheduler

PROJECT_ROOT = Path(os.getenv("LOTO_OPS_PROJECT", str(Path(__file__).resolve().parents[2])))
RUNS_DIR = Path(os.getenv("LOTO_OPS_RUNS_DIR", str(PROJECT_ROOT / "runs")))
HANDOVER_DIR = Path(os.getenv("LOTO_HANDOVER_DIR", "/mnt/e/env/ts/shared-ai-memory/handovers"))
HANDOVER_PATH = HANDOVER_DIR / "latest_handover.json"


def _cmd_export_handover(args: argparse.Namespace) -> int:
    """Export handover data from the latest or specified run_manifest to handover JSON.

    If --run-id is provided, use that specific run. Otherwise, find the latest
    run_manifest.json in the runs directory.
    """
    runs_dir = RUNS_DIR

    # Determine which run_id to use
    run_id = args.run_id if args.run_id else _find_latest_run_id(runs_dir)
    if run_id is None:
        print("[ERROR] No run_manifest.json found in runs directory.", file=sys.stderr)
        return 1

    # Find the manifest file
    manifest_path = _find_manifest_path(runs_dir, run_id)
    if manifest_path is None:
        print(f"[ERROR] Run directory not found for run_id: {run_id}", file=sys.stderr)
        return 1

    # Load manifest
    try:
        with open(manifest_path) as f:
            manifest_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[ERROR] Failed to read manifest: {e}", file=sys.stderr)
        return 1

    # Build handover data
    handover_data = {
        "handover_id": f"ho_{datetime.now(UTC).isoformat()}",
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": manifest_data.get("run_id", ""),
        "status": manifest_data.get("status", "unknown"),
        "last_successful_stage": manifest_data.get("last_successful_stage"),
        "next_stage": _compute_next_stage(manifest_data),
        "artifacts": manifest_data.get("artifacts", []),
        "error_message": manifest_data.get("error_message", None),
    }

    # Write handover file
    HANDOVER_DIR.mkdir(parents=True, exist_ok=True)
    with open(HANDOVER_PATH, "w") as f:
        json.dump(handover_data, f, indent=2)

    print(f"[INFO] Handover exported to: {HANDOVER_PATH}")
    return 0


def _cmd_import_handover(args: argparse.Namespace) -> int:
    """Import and display handover data from latest_handover.json."""
    if not HANDOVER_PATH.exists():
        print("[ERROR] latest_handover.json not found.", file=sys.stderr)
        return 1

    try:
        with open(HANDOVER_PATH) as f:
            handover_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[ERROR] Failed to read handover file: {e}", file=sys.stderr)
        return 1

    # Pretty-print the handover data
    print(json.dumps(handover_data, indent=2, ensure_ascii=False))
    return 0


def _find_latest_run_id(runs_dir: Path) -> str | None:
    """Find the latest run_id by scanning runs directory for manifest files."""
    latest_run_id = None
    for d in runs_dir.iterdir():
        if d.is_dir():
            manifest_path = d / "run_manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        manifest_data = json.load(f)
                    run_id = manifest_data.get("run_id", "")
                    if run_id and (latest_run_id is None or run_id > latest_run_id):
                        latest_run_id = run_id
                except (json.JSONDecodeError, OSError):
                    continue
    return latest_run_id


def _find_manifest_path(runs_dir: Path, run_id: str) -> Path | None:
    """Find the manifest file path for a given run_id."""
    for d in runs_dir.iterdir():
        if d.is_dir() and d.name == run_id:
            manifest_path = d / "run_manifest.json"
            if manifest_path.exists():
                return manifest_path
    return None


def _compute_next_stage(manifest_data: dict) -> str | None:
    """Compute the next stage based on manifest status."""
    status = manifest_data.get("status", "unknown")
    manifest_data.get("last_successful_stage")
    errors = manifest_data.get("errors", [])

    if status == "success":
        return None  # All stages completed
    elif status == "failed":
        if errors:
            # Return the last failed stage
            return errors[-1].get("stage", "unknown")
        return None
    else:
        return None


def cmd_run_legacy(args: argparse.Namespace) -> int:
    """Run the legacy-compatible pipeline entry point."""
    from loto_ops.config import load_settings as runtime_load_settings
    from loto_ops.pipeline.orchestrator import (
        PipelineOrchestrator as RuntimePipelineOrchestrator,
    )

    try:
        settings = runtime_load_settings(getattr(args, "config", None))
    except Exception as exc:
        print(f"[ERROR] Failed to load configuration: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("[INFO] Dry-run mode: Configuration loaded successfully. Pipeline paths validated.")
        return 0

    orchestrator = RuntimePipelineOrchestrator(settings)
    try:
        default_games = settings.pipeline.get("default_games", "all")
        games = [default_games] if isinstance(default_games, str) else default_games
        results = orchestrator.run_pipeline(games)
        if not results:
            print("[ERROR] Pipeline returned no game results.", file=sys.stderr)
            return 1

        failed = {
            game: result
            for game, result in results.items()
            if not isinstance(result, dict) or result.get("status") not in {"success", "skipped"}
        }
        if failed:
            print(
                "[ERROR] Pipeline failed: " + json.dumps(failed, ensure_ascii=False),
                file=sys.stderr,
            )
            return 1

        print(f"[INFO] Pipeline completed: {results}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Pipeline failed: {exc}", file=sys.stderr)
        return 1


def _settings(args):
    return load_settings(args.config)


def cmd_preflight(args) -> int:
    settings = _settings(args)
    info = PipelineOrchestrator(settings).preflight(auto_fix=args.auto_fix)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info.get("status") in {"PASS", "PARTIAL"} else 2


def cmd_init_db(args) -> None:
    admin = DbAdmin(_settings(args))
    if args.create_database:
        admin.create_loto_database_if_missing()
    admin.init_schema()


def cmd_reset_tables(args) -> None:
    DbAdmin(_settings(args)).reset_pipeline_tables(confirm_reset=args.confirm_reset)


def cmd_scrape(args) -> None:
    ScraperRunner(_settings(args)).run(games=args.games, force=args.force)


def cmd_build_dataset(args) -> None:
    DatasetBuilder(_settings(args)).run()


def cmd_load_postgres(args) -> None:
    loader = CopyLoader(_settings(args))
    load_sql = loader.export_sqlite_to_csv_and_sql()
    print(load_sql)
    loader.run_psql_copy(load_sql)


def cmd_fix_exog(args) -> None:
    runner = ExogRunner(_settings(args))
    changed = runner.patch_sqlalchemy_inspect()
    print("patched" if changed else "no patch needed")


def cmd_build_exog(args) -> None:
    reporter = ProgressReporter("build-exog", ["build-exog"], enabled=not args.no_progress)
    run_step(
        reporter,
        "build-exog",
        ExogRunner(_settings(args)).run,
        parallel_workers=args.parallel_workers,
    )
    reporter.finish()


def cmd_build_unified(args) -> None:
    settings = _settings(args)
    if getattr(args, "engine", "fast") == "legacy":
        reporter = ProgressReporter(
            "build-unified", ["legacy build-unified"], enabled=not args.no_progress
        )
        run_step(reporter, "legacy build-unified", UnifiedRunner(settings).run)
        reporter.finish()
        return

    reporter = ProgressReporter(
        "build-unified-fast", ["plan", "postgres ctas", "verify"], enabled=not args.no_progress
    )
    try:
        reporter.start_step("plan")
        plan = ResourceGovernor(settings).make_plan(mode=args.mode)
        reporter.complete_step(plan.reason)
        reporter.start_step("postgres ctas")
        out = UnifiedFastBuilder(settings).build(
            mode=args.mode,
            max_exog_cols=args.max_exog_cols,
            include_tables=args.include_exog_table,
            unlogged=not args.logged,
        )
        reporter.complete_step(f"rows={out.rows} cols={out.columns}")
        reporter.start_step("verify")
        reporter.complete_step("done")
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.finish()
    print(json.dumps(out.to_dict(), ensure_ascii=False, indent=2))


def cmd_build_unified_fast(args) -> None:
    cmd_build_unified(args)


def cmd_analyze(args) -> None:
    settings = _settings(args)
    reporter = ProgressReporter(
        "analyze", ["profile tables", "write reports"], enabled=not args.no_progress
    )
    reporter.start_step("profile tables")
    try:
        profiles = profile_important_tables(settings)
        reporter.complete_step()
        reporter.start_step("write reports")
        out = write_quality_reports(settings, profiles)
        reporter.complete_step()
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.finish()
    print(json.dumps({k: str(v) for k, v in out.items()}, ensure_ascii=False, indent=2))


def cmd_package(args) -> None:
    reporter = ProgressReporter(
        f"package-{args.mode}", ["create zip"], enabled=not args.no_progress
    )
    reporter.start_step("create zip")
    try:
        out = ArtifactPackager(_settings(args)).create_zip(run_id=args.run_id, mode=args.mode)
        reporter.complete_step()
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.finish()
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_run_all(args) -> None:
    settings = _settings(args)
    manifest = PipelineOrchestrator(settings).run_all(
        with_exog=args.with_exog,
        allow_no_exog=args.allow_no_exog,
        with_analysis=args.with_analysis,
        with_zip=args.with_zip,
        games=args.games,
    )
    print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))


def cmd_build_dataset_fast(args) -> None:
    reporter = ProgressReporter(
        "build-dataset-fast", ["build dataset", "write artifacts"], enabled=not args.no_progress
    )
    reporter.start_step("build dataset")
    try:
        out = FastDatasetBuilder(_settings(args)).run(
            engine=args.engine, export_parquet=not args.no_parquet
        )
        reporter.complete_step(f"rows={out.get('rows')}")
        reporter.start_step("write artifacts")
        reporter.complete_step("artifacts ready")
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.finish()
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_load_postgres_fast(args) -> None:
    loader = FastCopyLoader(_settings(args))
    reporter = ProgressReporter(
        "load-postgres-fast",
        ["prepare csv/sql", "copy partitions", "promote tables"],
        enabled=not args.no_progress,
    )
    reporter.start_step("prepare csv/sql")
    try:
        if args.prepare_only:
            out = loader.export_partitioned_sqlite_to_csv_and_sql(partition_by=args.partition_by)
            reporter.complete_step()
            reporter.start_step("copy partitions")
            reporter.complete_step("prepare-only skipped")
            reporter.start_step("promote tables")
            reporter.complete_step("prepare-only skipped")
        else:
            reporter.complete_step()
            reporter.start_step("copy partitions")
            out = loader.run_parallel_copy(jobs=args.jobs, show_progress=not args.no_progress)
            reporter.complete_step()
            reporter.start_step("promote tables")
            reporter.complete_step("promoted by loader")
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.finish()
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_recover_base_tables(args) -> None:
    """Recover dataset.loto_y_ts and dataset.loto_hist_feat from SQLite via parallel COPY."""
    reporter = ProgressReporter(
        "recover-base-tables", ["copy base tables"], enabled=not args.no_progress
    )
    reporter.start_step("copy base tables")
    try:
        loader = FastCopyLoader(_settings(args))
        out = loader.run_parallel_copy(jobs=args.jobs, show_progress=not args.no_progress)
        reporter.complete_step()
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.finish()
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_run_all_fast(args) -> None:
    settings = _settings(args)
    plan = ResourceGovernor(settings).make_plan(mode=args.mode)
    jobs = args.jobs or plan.copy_jobs
    parallel_workers = args.parallel_workers or plan.exog_workers
    steps = [
        "build dataset" if not args.reuse_sqlite else "validate sqlite",
        "load postgres",
    ]
    if args.with_exog:
        steps.append("build exog")
    steps.append("build unified fast" if args.unified_engine == "fast" else "build unified legacy")
    if args.with_analysis:
        steps.append("analyze")
    if args.package:
        steps.append(f"package {args.package}")

    state_path = settings.paths.ops_project / "logs" / "pipeline_progress.json"
    reporter = ProgressReporter(
        "run-all-fast", steps, state_path=state_path, enabled=not args.no_progress
    )
    out: dict[str, object] = {"plan": plan.to_dict()}
    try:
        if args.reuse_sqlite:
            run_step(reporter, "validate sqlite", DatasetBuilder(settings).validate_sqlite_dataset)
        else:
            out["build_dataset"] = run_step(
                reporter, "build dataset", FastDatasetBuilder(settings).run, engine=args.engine
            )
        loader = FastCopyLoader(settings)
        out["load_postgres"] = run_step(
            reporter,
            "load postgres",
            loader.run_parallel_copy,
            jobs=jobs,
            show_progress=not args.no_progress,
        )
        if args.with_exog:
            run_step(
                reporter, "build exog", ExogRunner(settings).run, parallel_workers=parallel_workers
            )
        if args.unified_engine == "legacy":
            run_step(reporter, "build unified legacy", UnifiedRunner(settings).run)
        else:
            reporter.start_step("build unified fast")
            unified = UnifiedFastBuilder(settings).build(
                mode=args.mode, max_exog_cols=args.max_exog_cols, unlogged=not args.logged
            )
            out["unified"] = unified.to_dict()
            reporter.complete_step(f"rows={unified.rows} cols={unified.columns}")
        if args.with_analysis:
            reporter.start_step("analyze")
            profiles = profile_important_tables(settings)
            out["analysis"] = {
                k: str(v) for k, v in write_quality_reports(settings, profiles).items()
            }
            reporter.complete_step()
        if args.package:
            reporter.start_step(f"package {args.package}")
            out["package"] = ArtifactPackager(settings).create_zip(
                run_id=args.run_id, mode=args.package
            )
            reporter.complete_step()
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.finish()
    if out:
        print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_perf_status(args) -> None:
    settings = _settings(args)
    governor = ResourceGovernor(settings)
    if args.shell:
        governor.print_shell_exports(mode=args.mode)
        return
    out = governor.diagnostics(mode=args.mode)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        plan = out["plan"]
        print("=== performance plan ===")
        for key, value in plan.items():
            print(f"{key}: {value}")
        print("\n=== shell env ===")
        for key, value in out["plan_env"].items():
            print(f"export {key}={json.dumps(value)}")
        print("\n=== large tables ===")
        for row in out.get("tables", [])[:20]:
            print(
                f"{row['schema']}.{row['table']}: rows≈{row['estimated_rows']} size={row['size_mb']}MB"
            )


def cmd_exog_mode(args) -> None:
    manager = ExogModeManager(_settings(args))
    if args.action == "status":
        out = {"action": "status", "status": manager.status()}
    elif args.action == "light":
        out = manager.set_light().to_dict()
    elif args.action == "full":
        out = manager.set_full().to_dict()
    else:
        raise SystemExit(f"unknown action: {args.action}")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_optimize_db(args) -> None:
    settings = _settings(args)
    db = settings.db
    env = os.environ.copy()
    env["PGPASSWORD"] = db.password
    commands = []
    if args.refresh_collation:
        commands.append(
            [*db.psql_base_args, "-c", f"ALTER DATABASE {db.database} REFRESH COLLATION VERSION;"]
        )
    if args.reindex:
        commands.append([*db.psql_base_args, "-c", f"REINDEX DATABASE {db.database};"])
    if args.analyze:
        commands.append([*db.psql_base_args, "-c", "ANALYZE;"])
    if not commands:
        print("No action selected. Use --refresh-collation, --reindex, or --analyze.")
        return
    for cmd in commands:
        print("[run]", " ".join(cmd))
        subprocess.run(cmd, env=env, check=True)


def cmd_benchmark_stages(args) -> None:
    settings = _settings(args)
    plan = ResourceGovernor(settings).make_plan(mode=args.mode)
    steps = []
    if args.include_dataset:
        steps.append(["loto-ops", "build-dataset-fast", "--engine", args.engine])
    if args.include_load:
        steps.append(["loto-ops", "load-postgres-fast", "--jobs", str(args.jobs or plan.copy_jobs)])
    if args.include_exog:
        steps.append(
            [
                "loto-ops",
                "build-exog",
                "--parallel-workers",
                str(args.parallel_workers or plan.exog_workers),
            ]
        )
    if args.include_unified:
        steps.append(["loto-ops", "build-unified", "--engine", "fast", "--mode", args.mode])
    if args.include_analyze:
        steps.append(["loto-ops", "analyze"])
    if not steps:
        steps = [["loto-ops", "perf-status", "--mode", args.mode]]
    results = []
    for cmd in steps:
        started = __import__("time").perf_counter()
        rc = subprocess.run(cmd, cwd=settings.paths.ops_project).returncode
        seconds = round(__import__("time").perf_counter() - started, 3)
        results.append({"cmd": cmd, "returncode": rc, "seconds": seconds})
        if rc != 0 and not args.keep_going:
            break
    print(
        json.dumps(
            {"mode": args.mode, "plan": plan.to_dict(), "results": results},
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_benchmark_probe(args) -> None:
    out = BenchmarkRunner(_settings(args)).write_system_probe_script()
    print(out)


def _is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _find_available_port(start_port: int, host: str = "127.0.0.1", max_tries: int = 100) -> int:
    for port in range(start_port, start_port + max_tries):
        if _is_port_available(port, host=host):
            return port
    raise RuntimeError(
        f"No available port found in range {start_port}-{start_port + max_tries - 1}"
    )


def cmd_webapp(args) -> None:
    if shutil.which("streamlit") is None:
        print("[loto-ops] Streamlit が未導入です。Webアプリを使う場合は以下を実行してください。")
        print("  ./scripts/setup_web.sh")
        print("または:")
        print("  uv sync --no-dev --extra web")
        raise SystemExit(2)

    settings = _settings(args)
    app_path = settings.paths.ops_project / "src" / "loto_ops" / "webapp" / "app.py"

    requested_port = int(args.port)
    host = args.host
    port = requested_port

    if args.auto_port:
        port = _find_available_port(requested_port, host="127.0.0.1", max_tries=args.port_scan)
        if port != requested_port:
            print(f"[loto-ops] port {requested_port} is busy; using {port}")
    elif not _is_port_available(requested_port, host="127.0.0.1"):
        print(f"[loto-ops] port {requested_port} is busy.")
        print(f"[loto-ops] try: loto-ops webapp --port {requested_port + 1} --auto-port")
        raise SystemExit(2)

    print(f"[loto-ops] webapp: http://127.0.0.1:{port}")
    subprocess.run(
        [
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            host,
            "--server.port",
            str(port),
        ],
        check=True,
    )


def cmd_path_status(args) -> None:
    """Print configured external project paths and whether they exist."""
    settings = _settings(args)
    paths = {
        "ops_project": settings.paths.ops_project,
        "loto_life_project": settings.paths.loto_life_project,
        "loto_forecast_project": settings.paths.loto_forecast_project,
        "zip_output_dir": settings.paths.zip_output_dir,
        "sqlite_path": settings.paths.sqlite_path,
        "postgres_load_dir": settings.paths.postgres_load_dir,
    }
    out = {}
    for name, path in paths.items():
        out[name] = {
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
            "is_file": path.is_file(),
        }
    candidates = [
        str(settings.paths.ops_project.parent / "loto_life_feature_pipeline"),
        "/mnt/e/env/ts/loto_life_feature_pipeline",
        "/mnt/e/env/ts/codex/loto_life_feature_pipeline",
        "/mnt/e/env/fc/loto_life_feature_pipeline",
        "/mnt/e/env/fc/old/loto_life_feature_pipeline",
    ]
    out["loto_life_candidates"] = [{"path": c, "exists": Path(c).exists()} for c in candidates]
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for name, info in out.items():
            if isinstance(info, list):
                print(f"{name}:")
                for item in info:
                    print(f"  {'OK' if item['exists'] else 'NG'} {item['path']}")
            else:
                print(f"{name}: {'OK' if info['exists'] else 'NG'} {info['path']}")


def cmd_schedule_install(args) -> None:
    out = SystemdUserScheduler(_settings(args)).install(time_str=args.time)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("systemctl --user daemon-reload")
    print(f"systemctl --user enable --now {out.get('unit_name', 'loto-ops-weekday')}.timer")


def _run_project_script(settings, script_name: str, *args: str) -> None:
    script = settings.paths.ops_project / "scripts" / script_name
    if not script.exists():
        raise FileNotFoundError(f"script not found: {script}")
    env = os.environ.copy()
    env.setdefault("LOTO_OPS_CONFIG", str(settings.paths.ops_project / "configs" / "loto_ops.yaml"))
    subprocess.run(
        ["bash", str(script), *args], cwd=settings.paths.ops_project, env=env, check=True
    )


def cmd_schedule_install_cron(args) -> None:
    """Install user crontab entries for weekday midnight and @reboot."""
    _run_project_script(_settings(args), "install_cron_schedule.sh")


def cmd_schedule_install_kubuntu_startup(args) -> None:
    """Install Kubuntu user startup hooks."""
    _run_project_script(_settings(args), "install_kubuntu_startup.sh")


def cmd_schedule_install_wsl_startup(args) -> None:
    """Install WSL startup helpers."""
    extra = ["--write-wsl-conf"] if args.write_wsl_conf else []
    _run_project_script(_settings(args), "install_wsl_startup.sh", *extra)


def cmd_schedule_status(args) -> None:
    """Print schedule and last-run status."""
    _run_project_script(_settings(args), "check_schedule.sh")


def cmd_schedule_run_now(args) -> None:
    """Run scheduled pipeline immediately."""
    _run_project_script(_settings(args), "run_scheduled_pipeline.sh", args.reason)


def cmd_notify_run_summary(args) -> None:
    settings = _settings(args)
    builder = RunSummaryBuilder(settings)
    summary = builder.build(
        status=args.status,
        reason=args.reason,
        log_file=Path(args.log_file) if args.log_file else None,
        progress_file=Path(args.progress_file) if args.progress_file else None,
        last_run_file=Path(args.last_run_file) if args.last_run_file else None,
        include_log_tail=not args.no_log_tail,
    )
    results = NotificationSender().send_all(summary, fail_on_error=args.fail_on_error)
    print(
        json.dumps(
            {"summary": summary, "notifications": [r.to_dict() for r in results]},
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_notify_test(args) -> None:
    settings = _settings(args)
    summary = RunSummaryBuilder(settings).build(
        status="test",
        reason=args.reason,
        include_log_tail=False,
    )
    summary["message"] = args.message
    results = NotificationSender().send_all(summary, fail_on_error=args.fail_on_error)
    print(
        json.dumps(
            {"summary": summary, "notifications": [r.to_dict() for r in results]},
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="loto-ops")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(required=True)

    sp = sub.add_parser("preflight")
    sp.add_argument("--auto-fix", action="store_true")
    sp.set_defaults(func=cmd_preflight)

    sp = sub.add_parser("init-db")
    sp.add_argument("--create-database", action="store_true")
    sp.set_defaults(func=cmd_init_db)

    sp = sub.add_parser("reset-tables")
    sp.add_argument("--confirm-reset", action="store_true")
    sp.set_defaults(func=cmd_reset_tables)

    sp = sub.add_parser("scrape")
    sp.add_argument("--games", default="all")
    sp.add_argument("--force", action="store_true", default=True)
    sp.set_defaults(func=cmd_scrape)

    sp = sub.add_parser("build-dataset")
    sp.set_defaults(func=cmd_build_dataset)

    sp = sub.add_parser("load-postgres")
    sp.set_defaults(func=cmd_load_postgres)

    sp = sub.add_parser("fix-exog")
    sp.set_defaults(func=cmd_fix_exog)

    sp = sub.add_parser("build-exog")
    sp.add_argument("--parallel-workers", type=int, default=4)
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_build_exog)

    sp = sub.add_parser("build-unified")
    sp.add_argument("--engine", choices=["fast", "legacy"], default="fast")
    sp.add_argument("--mode", choices=["light", "full", "auto"], default="light")
    sp.add_argument("--max-exog-cols", type=int, default=None)
    sp.add_argument("--include-exog-table", action="append", default=None)
    sp.add_argument(
        "--logged", action="store_true", help="Create logged table instead of UNLOGGED staging"
    )
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_build_unified)

    sp = sub.add_parser("build-unified-fast")
    sp.add_argument("--mode", choices=["light", "full", "auto"], default="light")
    sp.add_argument("--max-exog-cols", type=int, default=None)
    sp.add_argument("--include-exog-table", action="append", default=None)
    sp.add_argument("--logged", action="store_true")
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_build_unified_fast)

    sp = sub.add_parser("analyze")
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("package")
    sp.add_argument("--mode", choices=["light", "full"], default="light")
    sp.add_argument("--run-id", default=None)
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_package)

    sp = sub.add_parser("run-all")
    sp.add_argument("--games", default="all")
    sp.add_argument("--with-exog", action="store_true")
    sp.add_argument("--allow-no-exog", action="store_true", default=True)
    sp.add_argument("--with-analysis", action="store_true")
    sp.add_argument("--with-zip", action="store_true")
    sp.set_defaults(func=cmd_run_all)

    sp = sub.add_parser("build-dataset-fast")
    sp.add_argument("--engine", choices=["auto", "polars", "pandas"], default="auto")
    sp.add_argument("--no-parquet", action="store_true")
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_build_dataset_fast)

    sp = sub.add_parser("load-postgres-fast")
    sp.add_argument("--jobs", type=int, default=None)
    sp.add_argument("--partition-by", default="loto")
    sp.add_argument("--prepare-only", action="store_true")
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_load_postgres_fast)

    sp = sub.add_parser("recover-base-tables")
    sp.add_argument("--jobs", type=int, default=None)
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_recover_base_tables)

    sp = sub.add_parser("run-all-fast")
    sp.add_argument("--engine", choices=["auto", "polars", "pandas"], default="auto")
    sp.add_argument("--mode", choices=["light", "full", "auto"], default="light")
    sp.add_argument("--unified-engine", choices=["fast", "legacy"], default="fast")
    sp.add_argument("--max-exog-cols", type=int, default=None)
    sp.add_argument("--jobs", type=int, default=None)
    sp.add_argument("--reuse-sqlite", action="store_true")
    sp.add_argument("--with-exog", action="store_true")
    sp.add_argument("--parallel-workers", type=int, default=None)
    sp.add_argument("--with-analysis", action="store_true")
    sp.add_argument("--package", choices=["light", "full"], default=None)
    sp.add_argument("--run-id", default=None)
    sp.add_argument("--logged", action="store_true")
    sp.add_argument("--no-progress", action="store_true")
    sp.set_defaults(func=cmd_run_all_fast)

    sp = sub.add_parser("benchmark-probe")
    sp.set_defaults(func=cmd_benchmark_probe)

    sp = sub.add_parser("perf-status")
    sp.add_argument("--mode", choices=["light", "full", "auto"], default="auto")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--shell", action="store_true")
    sp.set_defaults(func=cmd_perf_status)

    sp = sub.add_parser("exog-mode")
    sp.add_argument("action", choices=["status", "light", "full"])
    sp.set_defaults(func=cmd_exog_mode)

    sp = sub.add_parser("optimize-db")
    sp.add_argument("--refresh-collation", action="store_true")
    sp.add_argument("--reindex", action="store_true")
    sp.add_argument("--analyze", action="store_true")
    sp.set_defaults(func=cmd_optimize_db)

    sp = sub.add_parser("benchmark-stages")
    sp.add_argument("--mode", choices=["light", "full", "auto"], default="light")
    sp.add_argument("--engine", choices=["auto", "polars", "pandas"], default="auto")
    sp.add_argument("--jobs", type=int, default=None)
    sp.add_argument("--parallel-workers", type=int, default=None)
    sp.add_argument("--include-dataset", action="store_true")
    sp.add_argument("--include-load", action="store_true")
    sp.add_argument("--include-exog", action="store_true")
    sp.add_argument("--include-unified", action="store_true", default=True)
    sp.add_argument("--include-analyze", action="store_true")
    sp.add_argument("--keep-going", action="store_true")
    sp.set_defaults(func=cmd_benchmark_stages)

    sp = sub.add_parser("path-status")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_path_status)

    sp = sub.add_parser("webapp")
    sp.add_argument("--port", type=int, default=8520)
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--auto-port", action="store_true", default=True)
    sp.add_argument("--no-auto-port", dest="auto_port", action="store_false")
    sp.add_argument("--port-scan", type=int, default=100)
    sp.set_defaults(func=cmd_webapp)

    sp = sub.add_parser("notify-run-summary")
    sp.add_argument("--status", default=None)
    sp.add_argument("--reason", default=None)
    sp.add_argument("--log-file", default=None)
    sp.add_argument("--progress-file", default=None)
    sp.add_argument("--last-run-file", default=None)
    sp.add_argument("--no-log-tail", action="store_true")
    sp.add_argument("--fail-on-error", action="store_true")
    sp.set_defaults(func=cmd_notify_run_summary)

    sp = sub.add_parser("notify-test")
    sp.add_argument("--reason", default="manual_notify_test")
    sp.add_argument("--message", default="Loto Ops notification test")
    sp.add_argument("--fail-on-error", action="store_true")
    sp.set_defaults(func=cmd_notify_test)

    sp = sub.add_parser("schedule-install")
    sp.add_argument("--time", default="06:30")
    sp.set_defaults(func=cmd_schedule_install)

    sp = sub.add_parser("schedule-install-cron")
    sp.set_defaults(func=cmd_schedule_install_cron)

    sp = sub.add_parser("schedule-install-kubuntu-startup")
    sp.set_defaults(func=cmd_schedule_install_kubuntu_startup)

    sp = sub.add_parser("schedule-install-wsl-startup")
    sp.add_argument("--write-wsl-conf", action="store_true")
    sp.set_defaults(func=cmd_schedule_install_wsl_startup)

    sp = sub.add_parser("schedule-status")
    sp.set_defaults(func=cmd_schedule_status)

    sp = sub.add_parser("schedule-run-now")
    sp.add_argument("--reason", default="manual")
    sp.set_defaults(func=cmd_schedule_run_now)

    sp = sub.add_parser(
        "run",
        help="Run the pipeline through the legacy-compatible entry point",
    )
    sp.add_argument("--with-exog", action="store_true", help="Include exogenous features")
    sp.add_argument("--dry-run", action="store_true", help="Validate configuration without running")
    sp.add_argument("--skip-clean", action="store_true", help="Skip cleanup of previous artifacts")
    sp.set_defaults(func=cmd_run_legacy)

    sp = sub.add_parser("export-handover", help="Export pipeline state to shared handover")
    sp.add_argument("--run-id", default=None, help="Specific run ID; defaults to latest")
    sp.set_defaults(func=_cmd_export_handover)

    sp = sub.add_parser("import-handover", help="Display the latest shared handover")
    sp.set_defaults(func=_cmd_import_handover)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
