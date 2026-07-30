from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from loto.data.canonical import canonicalize_loto7
from loto.data.integrated import acquire_and_build, acquire_and_build_many
from loto.experiment_config import ExperimentConfig
from loto.models.catalog import list_model_specs
from loto.orchestration.research import run_research_experiment
from loto.coverage.runner import certify_coverage_experiment, run_coverage_experiment
from loto.coverage.auto_research import certify_auto_research, run_auto_research
from loto.evaluation.shadow import score_combination
from loto.orchestration.pipeline import run_trusted_vertical_slice
from loto.registry.artifacts import ArtifactStore
from loto.registry.full import PlatformRegistry
from loto.registry.release import verify_release_bundle
from loto.sealing.manifest import verify_seal
from loto.notifications import NotificationSender, build_run_summary, write_notification_report
from loto.scheduling import SchedulePolicy, build_schedule_plan, write_schedule_plan


def _secret() -> bytes:
    value = os.environ.get("LOTO_SEAL_SECRET")
    if not value:
        raise SystemExit("LOTO_SEAL_SECRET is required")
    return value.encode()


def _json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _probe_torch(timeout_seconds: int = 10) -> dict:
    script = """import json,torch; print(json.dumps({'torch':torch.__version__,'cuda_available':torch.cuda.is_available(),'cuda_device_count':torch.cuda.device_count(),'cuda_version':torch.version.cuda}))"""
    try:
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                              timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"torch_probe_timeout": True, "timeout_seconds": timeout_seconds}
    if proc.returncode != 0:
        return {"torch_probe_error": True, "returncode": proc.returncode, "stderr": proc.stderr[-1000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"torch_probe_error": True, "stdout": proc.stdout[-1000:]}


def _registry(args) -> PlatformRegistry:
    return PlatformRegistry(args.registry)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loto")
    parser.add_argument("--registry", default=os.environ.get("LOTO_REGISTRY_URL", "platform.sqlite3"))
    sub = parser.add_subparsers(dest="group", required=True)

    data = sub.add_parser("data"); dsub = data.add_subparsers(dest="action", required=True)
    val = dsub.add_parser("validate"); val.add_argument("--input", required=True)
    acquire = dsub.add_parser("acquire")
    acquire.add_argument("--game", default="loto7", help="single game key; use --games for several")
    acquire.add_argument("--games", help="comma-separated game keys or all")
    acquire.add_argument("--output", required=True)
    acquire.add_argument("--source-file", help="local source for single-game mode")
    acquire.add_argument("--source-map", help="JSON object mapping game keys to local source files")
    acquire.add_argument("--force", action="store_true")
    acquire.add_argument("--postgres-dsn")
    acquire.add_argument("--require-parquet", action="store_true")
    acquire.add_argument("--fail-fast", action="store_true")

    exp = sub.add_parser("experiment"); esub = exp.add_subparsers(dest="action", required=True)
    run = esub.add_parser("run"); run.add_argument("--input", required=True); run.add_argument("--output", required=True); run.add_argument("--backtest-draws", type=int, default=20)
    full_run = esub.add_parser("run-all"); full_run.add_argument("--game", default="loto7"); full_run.add_argument("--output", required=True); full_run.add_argument("--source-file"); full_run.add_argument("--force", action="store_true"); full_run.add_argument("--postgres-dsn"); full_run.add_argument("--backtest-draws", type=int, default=20)
    status = esub.add_parser("status"); status.add_argument("--limit", type=int, default=50)
    research = esub.add_parser("research"); research.add_argument("--config", required=True)
    coverage = esub.add_parser("coverage"); coverage.add_argument("--config", required=True); coverage.add_argument("--certify", action="store_true"); coverage.add_argument("--prediction-set")
    auto_cov = esub.add_parser("auto-coverage"); auto_cov.add_argument("--config", required=True); auto_cov.add_argument("--certify", action="store_true")

    models = sub.add_parser("models"); msub = models.add_subparsers(dest="action", required=True)
    mlist = msub.add_parser("list"); mlist.add_argument("--priority"); mlist.add_argument("--available-only", action="store_true"); mlist.add_argument("--format", choices=["json","table"], default="table")
    mshow = msub.add_parser("show"); mshow.add_argument("model_id")

    config = sub.add_parser("config"); csub = config.add_subparsers(dest="action", required=True)
    cval = csub.add_parser("validate"); cval.add_argument("--file", required=True); cval.add_argument("--write-resolved")

    fc = sub.add_parser("forecast"); fsub = fc.add_subparsers(dest="action", required=True)
    verify = fsub.add_parser("verify"); verify.add_argument("--manifest", required=True)
    score = fsub.add_parser("score"); score.add_argument("--forecast", required=True); score.add_argument("--actual", nargs=7, type=int, required=True)

    artifact = sub.add_parser("artifact"); asub = artifact.add_subparsers(dest="action", required=True)
    put = asub.add_parser("put"); put.add_argument("--file", required=True); put.add_argument("--store", required=True); put.add_argument("--namespace", default="default")
    verify_bundle = asub.add_parser("verify-bundle"); verify_bundle.add_argument("--bundle", required=True)

    approval = sub.add_parser("approval"); apsub = approval.add_subparsers(dest="action", required=True)
    req = apsub.add_parser("request"); req.add_argument("--type", required=True); req.add_argument("--id", required=True); req.add_argument("--operation", required=True); req.add_argument("--actor", required=True); req.add_argument("--reason", required=True)
    dec = apsub.add_parser("decide"); dec.add_argument("--type", required=True); dec.add_argument("--id", required=True); dec.add_argument("--operation", required=True); dec.add_argument("--actor", required=True); dec.add_argument("--approve", action="store_true")

    notify = sub.add_parser("notify"); nsub = notify.add_subparsers(dest="action", required=True)
    preview = nsub.add_parser("preview"); preview.add_argument("--report", required=True); preview.add_argument("--output-dir")
    send = nsub.add_parser("send"); send.add_argument("--report", required=True); send.add_argument("--output-dir"); send.add_argument("--fail-on-error", action="store_true")

    schedule = sub.add_parser("schedule"); schsub = schedule.add_subparsers(dest="action", required=True)
    plan = schsub.add_parser("plan"); plan.add_argument("--games", default="all"); plan.add_argument("--policy"); plan.add_argument("--now"); plan.add_argument("--write")

    system = sub.add_parser("system"); ssub = system.add_subparsers(dest="action", required=True)
    ssub.add_parser("doctor")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.group == "data" and args.action == "validate":
        import pandas as pd
        _, manifest = canonicalize_loto7(pd.read_csv(args.input), source=args.input)
        print(manifest.model_dump_json(indent=2)); return 0
    if args.group == "data" and args.action == "acquire":
        games = args.games or args.game
        if args.games or games == "all" or "," in games:
            source_map = json.loads(Path(args.source_map).read_text(encoding="utf-8")) if args.source_map else None
            _json(acquire_and_build_many(
                games=games, output_dir=args.output, source_files=source_map, force=args.force,
                postgres_dsn=args.postgres_dsn, require_parquet=args.require_parquet,
                continue_on_error=not args.fail_fast,
            ))
        else:
            _json(acquire_and_build(
                game=games, output_dir=args.output, source_file=args.source_file, force=args.force,
                postgres_dsn=args.postgres_dsn, require_parquet=args.require_parquet,
            ))
        return 0
    if args.group == "experiment" and args.action == "run-all":
        if args.game != "loto7": raise SystemExit("experiment run-all currently supports loto7 prediction; data acquire supports all configured games")
        data_dir = Path(args.output) / "data"
        acquired = acquire_and_build(game=args.game, output_dir=data_dir, source_file=args.source_file, force=args.force, postgres_dsn=args.postgres_dsn)
        normalized = acquired["normalized"]
        result = run_trusted_vertical_slice(normalized, Path(args.output) / "forecast", secret=_secret(), backtest_draws=args.backtest_draws)
        _json({"acquisition": acquired, "forecasting": result}); return 0
    if args.group == "experiment" and args.action == "run":
        result = run_trusted_vertical_slice(args.input, args.output, secret=_secret(), backtest_draws=args.backtest_draws)
        _json(result); return 0
    if args.group == "experiment" and args.action == "status":
        _json(_registry(args).list_rows("runs", args.limit)); return 0
    if args.group == "experiment" and args.action == "research":
        cfg = ExperimentConfig.from_file(args.config); _json(run_research_experiment(cfg)); return 0
    if args.group == "experiment" and args.action == "auto-coverage":
        _json(certify_auto_research(args.config) if args.certify else run_auto_research(args.config)); return 0
    if args.group == "experiment" and args.action == "coverage":
        if args.certify:
            _json(certify_coverage_experiment(args.config, args.prediction_set))
        else:
            _json(run_coverage_experiment(args.config))
        return 0
    if args.group == "models" and args.action == "list":
        rows = [spec.to_dict() for spec in list_model_specs(priority=args.priority, available_only=args.available_only)]
        if args.format == "json": _json(rows)
        else:
            print(f"{'MODEL ID':32} {'LIBRARY':18} {'TASK':18} {'PRI':4} AVAILABLE")
            for row in rows: print(f"{row['model_id'][:32]:32} {row['library'][:18]:18} {row['task'][:18]:18} {row['priority']:4} {row['available']}")
        return 0
    if args.group == "models" and args.action == "show":
        from loto.models.catalog import get_model_spec
        _json(get_model_spec(args.model_id).to_dict()); return 0
    if args.group == "config" and args.action == "validate":
        cfg = ExperimentConfig.from_file(args.file)
        if args.write_resolved: cfg.write_resolved(args.write_resolved)
        _json({"valid": True, "config_hash": cfg.config_hash, "models": cfg.models}); return 0
    if args.group == "forecast" and args.action == "verify":
        ok = verify_seal(json.loads(Path(args.manifest).read_text()), _secret()); _json({"verified": ok}); return 0 if ok else 2
    if args.group == "forecast" and args.action == "score":
        package = json.loads(Path(args.forecast).read_text()); result = score_combination(package["combination"]["numbers"], args.actual); _json(result); return 0
    if args.group == "artifact" and args.action == "put":
        _json(ArtifactStore(args.store).put_file(args.file, namespace=args.namespace)); return 0
    if args.group == "artifact" and args.action == "verify-bundle":
        ok = verify_release_bundle(args.bundle); _json({"verified": ok, "errors": [] if ok else ["bundle hash or artifact mismatch"]}); return 0 if ok else 2
    if args.group == "approval":
        reg = _registry(args)
        if args.action == "request":
            reg.request_approval(args.type, args.id, args.operation, args.actor, args.reason); _json({"status": "PENDING"}); return 0
        reg.decide_approval(args.type, args.id, args.operation, args.actor, args.approve); _json({"status": "APPROVED" if args.approve else "REJECTED"}); return 0
    if args.group == "notify":
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        summary = build_run_summary(report, output_dir=args.output_dir)
        if args.action == "preview":
            _json(summary)
            return 0
        sender = NotificationSender(base_dir=args.output_dir or Path(args.report).parent)
        results = sender.send_all(summary, fail_on_error=args.fail_on_error)
        status_path = Path(args.output_dir or Path(args.report).parent) / "notification_status.json"
        write_notification_report(results, status_path)
        _json({"summary": summary, "results": [item.to_dict() for item in results], "status_path": str(status_path)})
        return 0
    if args.group == "schedule" and args.action == "plan":
        from datetime import datetime
        policy = SchedulePolicy.from_file(args.policy) if args.policy else SchedulePolicy()
        now = datetime.fromisoformat(args.now) if args.now else None
        plan = build_schedule_plan(args.games, now=now, policy=policy)
        if args.write:
            write_schedule_plan(plan, args.write)
            plan["written_to"] = args.write
        _json(plan)
        return 0
    if args.group == "system":
        model_specs = list_model_specs()
        info = {
            "python": sys.version,
            "platform": platform.platform(),
            "registry": args.registry,
            "models_total": len(model_specs),
            "models_available": sum(item.available for item in model_specs),
            "configured_games": ["mini", "loto6", "loto7", "bingo5", "numbers3", "numbers4"],
            "notification_external_enabled": os.environ.get("LOTO_NOTIFY_ENABLED", "0") == "1",
        }
        if os.environ.get("LOTO_DEEP_DOCTOR") == "1": info.update(_probe_torch())
        else: info.update({"torch_probe_skipped": True, "deep_probe_hint": "Set LOTO_DEEP_DOCTOR=1"})
        _json(info); return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
