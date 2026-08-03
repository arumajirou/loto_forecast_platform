"""v3 command surface.

Kept separate from ``loto.cli`` so the v2 CLI regression tests stay valid. Every subcommand
prints JSON to stdout and returns a POSIX exit code, so the whole surface is scriptable and
CI-checkable without parsing prose.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from loto.evaluation.theory_general import bounds_table, theoretical_bounds
from loto.game.geometry import geometry_for, known_games
from loto.models.catalog_full import build_catalog, catalog_counts
from loto.models.revision_pins import (
    RevisionPinError,
    apply_manifest,
    revision_report,
    template_manifest,
    validate_manifest,
)
from loto.verify.integrity import generate_manifest, verify_manifest

__all__ = ["main", "build_parser"]


def _emit(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")


def _cmd_games(args: argparse.Namespace) -> int:
    _emit({g: geometry_for(g).to_dict() for g in known_games()})
    return 0


def _cmd_theory(args: argparse.Namespace) -> int:
    if args.game:
        _emit(theoretical_bounds(args.game, tau=args.tau).to_dict())
    else:
        _emit(bounds_table(tau=args.tau))
    return 0


def _cmd_catalog(args: argparse.Namespace) -> int:
    entries = build_catalog()
    if args.counts:
        _emit(catalog_counts())
        return 0
    rows = [e.to_row() for e in entries]
    if args.library:
        rows = [r for r in rows if r["library"] == args.library]
    if args.unpinned:
        rows = [r for r in rows if r["revision_status"] == "UNPINNED"]
    if args.csv:
        pd.DataFrame(rows).to_csv(args.csv, index=False)
        _emit({"written": args.csv, "rows": len(rows)})
        return 0
    _emit(rows)
    return 0


def _cmd_revisions(args: argparse.Namespace) -> int:
    entries = build_catalog()
    try:
        if args.action == "template":
            payload = template_manifest(entries)
            if args.output:
                Path(args.output).write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                _emit({"status": "WRITTEN", "path": args.output, "pins": len(payload["pins"])})
            else:
                _emit(payload)
            return 0
        if not args.manifest:
            raise RevisionPinError("--manifest is required for validate, report and apply")
        validate_manifest(args.manifest, entries, require_complete=args.require_complete)
        applied = apply_manifest(entries, args.manifest, require_complete=args.require_complete)
        if args.action == "validate":
            _emit({"status": "VALID", **revision_report(applied)})
            return 0
        if args.action == "report":
            _emit(revision_report(applied))
            return 0
        rows = [entry.to_row() for entry in applied]
        if not args.output:
            raise RevisionPinError("--output is required for apply")
        Path(args.output).write_text(
            json.dumps(rows, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
        )
        _emit({"status": "WRITTEN", "path": args.output, **revision_report(applied)})
        return 0
    except RevisionPinError as exc:
        _emit({"status": "INVALID", "error": str(exc)})
        return 2


def _cmd_integrity(args: argparse.Namespace) -> int:
    if args.action == "generate":
        payload = generate_manifest(args.root, release=args.release)
        _emit({k: v for k, v in payload.items() if k != "files"})
        return 0
    report = verify_manifest(args.root, strict_untracked=not args.allow_untracked)
    _emit(report.to_dict())
    return 0 if report.ok else 1


def _cmd_research(args: argparse.Namespace) -> int:
    from loto.orchestration.research_v3 import ResearchConfig, run_research

    geometry = geometry_for(args.game)
    if args.input:
        frame = pd.read_csv(args.input)
        version = f"{args.game}-{Path(args.input).stem}-{len(frame)}"
    else:
        rng = np.random.default_rng(args.seed)
        rows = []
        for i in range(args.synthetic_rows):
            if geometry.family == "select":
                values = sorted(
                    rng.choice(
                        np.arange(geometry.value_min, geometry.value_max + 1),
                        size=geometry.positions,
                        replace=False,
                    ).tolist()
                )
            else:
                values = rng.integers(
                    geometry.value_min, geometry.value_max + 1, size=geometry.positions
                ).tolist()
            rows.append(
                {"draw_no": i + 1, **dict(zip(geometry.column_names(), values, strict=False))}
            )
        frame = pd.DataFrame(rows)
        version = f"{args.game}-synthetic-{args.synthetic_rows}-seed{args.seed}"

    config = ResearchConfig(
        game=args.game,
        folds=args.folds,
        test_size=args.test_size,
        min_train_size=args.min_train_size,
        holdout_size=args.holdout_size,
        tau=args.tau,
        alpha=args.alpha,
        n_boot=args.n_boot,
        correction_method=args.correction,
    )
    outcome = run_research(frame, config, data_version=version)
    payload = outcome.to_dict()
    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "research_summary.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        pd.DataFrame(payload["leaderboard"]["rows"]).to_csv(
            out_dir / "model_leaderboard.csv", index=False
        )
        payload["artifacts"] = sorted(p.name for p in out_dir.iterdir())
    _emit(
        payload
        if args.verbose
        else {
            "status": payload["status"],
            "protocol_hash": payload["protocol_hash"],
            "verdict": payload["leaderboard"]["verdict"],
            "interpretation": payload["leaderboard"]["interpretation"],
            "champion": payload["leaderboard"]["champion"],
            "sentinel": payload["sentinel"]["status"],
            "statistical_power": payload["statistical_power"],
            "theory_mae_floor": payload["theory"]["mae_floor"],
            "holdout_evaluated": payload["holdout_evaluated"],
            "stage_status": payload["stage_status"],
            "warnings": payload["warnings"],
            "artifacts": payload.get("artifacts", []),
        }
    )
    return 0 if payload["status"] in ("SUCCEEDED", "PARTIALLY_SUCCEEDED") else 1


def _cmd_hierarchy(args: argparse.Namespace) -> int:
    from loto.reconciliation.hierarchy import build_number_hierarchy, reconcile

    geometry = geometry_for(args.game)
    hierarchy = build_number_hierarchy(geometry)
    rng = np.random.default_rng(args.seed)
    base = rng.uniform(0.0, 1.0, size=(hierarchy.n_total, 1))
    result = reconcile(base, hierarchy, method=args.method)
    _emit(
        {
            "game": args.game,
            "levels": hierarchy.n_total,
            "bottom_series": hierarchy.n_bottom,
            "labels_head": list(hierarchy.labels[:8]),
            "method": result["method"],
            "downgraded": result["downgraded_from_mint_shrink"],
            "base_incoherence": result["base_incoherence"],
            "coherence_error": result["coherence_error"],
        }
    )
    return 0



def _cmd_probabilistic(args: argparse.Namespace) -> int:
    from loto.probabilistic.backends import probe_backends
    from loto.probabilistic.catalog import (
        catalog_counts as ppl_catalog_counts,
        get_inference_profile,
        get_probabilistic_model_spec,
        list_inference_profiles,
        list_probabilistic_model_specs,
    )
    from loto.probabilistic.compatibility import decide_compatibility
    from loto.probabilistic.config import load_run_config
    from loto.probabilistic.planner import plan_summary
    from loto.probabilistic.native_registry import native_coverage, list_native_implementations
    from loto.probabilistic.runner import (
        compare_run,
        diagnose_run,
        load_status,
        run_probabilistic,
    )

    action = args.ppl_action
    if action == "catalog-list":
        rows = [
            spec.to_dict()
            for spec in list_probabilistic_model_specs(
                family=args.family, priority=args.priority
            )
        ]
        _emit({"counts": ppl_catalog_counts(), "models": rows})
        return 0
    if action == "catalog-show":
        try:
            _emit(get_probabilistic_model_spec(args.model_id).to_dict())
            return 0
        except KeyError:
            _emit({"status": "NOT_FOUND", "model_id": args.model_id})
            return 2
    if action == "profiles-list":
        _emit([profile.to_dict() for profile in list_inference_profiles(backend=args.backend)])
        return 0
    if action == "profiles-show":
        try:
            _emit(get_inference_profile(args.profile_id).to_dict())
            return 0
        except KeyError:
            _emit({"status": "NOT_FOUND", "profile_id": args.profile_id})
            return 2
    if action == "backends":
        _emit(probe_backends())
        return 0
    if action == "native-coverage":
        _emit({
            "coverage": native_coverage(),
            "implementations": [item.to_dict() for item in list_native_implementations()],
        })
        return 0
    if action == "compatibility":
        try:
            spec = get_probabilistic_model_spec(args.model_id)
            decision = decide_compatibility(
                spec,
                geometry=geometry_for(args.game),
                backend=args.backend,
                profile_id=args.profile_id,
                include_experimental=args.include_experimental,
            )
        except (KeyError, ValueError) as exc:
            _emit({"status": "INVALID", "error": str(exc)})
            return 2
        _emit(decision.to_dict())
        return 0 if decision.allowed else 3
    if action in {"validate-config", "plan", "smoke", "run"}:
        try:
            config = load_run_config(args.config)
            if action == "smoke":
                config = config.model_copy(update={"profile": "smoke"})
            elif action == "run" and config.profile == "smoke":
                config = config.model_copy(update={"profile": "standard"})
        except Exception as exc:
            _emit({"status": "CONFIG_INVALID", "error": f"{type(exc).__name__}: {exc}"})
            return 2
        if action == "validate-config":
            _emit({"status": "VALID", "config": config.model_dump(mode="json"), **plan_summary(config)})
            return 0
        if action == "plan":
            _emit(plan_summary(config))
            return 0
        result = run_probabilistic(config)
        _emit(result)
        return 0 if result["status"] in {"PASS", "DRY_RUN"} else 3
    if action == "status":
        try:
            _emit(load_status(args.run_dir))
            return 0
        except Exception as exc:
            _emit({"status": "NOT_FOUND", "error": str(exc)})
            return 2
    if action == "diagnose":
        try:
            _emit(diagnose_run(args.run_dir))
            return 0
        except Exception as exc:
            _emit({"status": "NOT_FOUND", "error": str(exc)})
            return 2
    if action == "compare":
        try:
            _emit(compare_run(args.run_dir))
            return 0
        except Exception as exc:
            _emit({"status": "NOT_FOUND", "error": str(exc)})
            return 2
    if action.startswith("api-") or action.startswith("tts-") or action.startswith("run-"):
        from loto.probabilistic.api_cli import (
            ApiClient,
            ProbabilisticApiCliError,
            create_api_environment,
            serve_api,
        )

        try:
            if action == "api-token-create":
                _emit(
                    create_api_environment(
                        args.root,
                        host=args.host,
                        port=args.port,
                        voicevox_url=args.voicevox_url,
                        force=args.force,
                    )
                )
                return 0
            if action == "api-serve":
                _emit(
                    {
                        "status": "STARTING",
                        "root": str(Path(args.root).resolve()),
                        "host": args.host,
                        "port": args.port,
                    }
                )
                serve_api(
                    root=args.root,
                    host=args.host,
                    port=args.port,
                    access_log=not args.no_access_log,
                )
                return 0

            client = ApiClient.from_environment(root=args.root, base_url=args.base_url)
            if action == "api-health":
                _emit(client.json("GET", "/health", authenticated=False))
                return 0
            if action == "api-profiles":
                _emit(client.json("GET", "/api/v1/profiles"))
                return 0
            if action == "tts-status":
                _emit(client.json("GET", "/api/v1/tts/status"))
                return 0
            if action == "tts-play":
                _emit(
                    client.json(
                        "POST",
                        "/api/v1/tts/play",
                        payload={
                            "text": args.text,
                            "speaker": args.speaker,
                            "speed_scale": args.speed_scale,
                        },
                        timeout=150.0,
                    )
                )
                return 0
            if action == "tts-synthesize":
                body, content_type = client.request(
                    "POST",
                    "/api/v1/tts/synthesize",
                    payload={
                        "text": args.text,
                        "speaker": args.speaker,
                        "speed_scale": args.speed_scale,
                    },
                    timeout=150.0,
                )
                output = Path(args.output).expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(body)
                _emit(
                    {
                        "status": "WRITTEN",
                        "path": str(output),
                        "bytes": len(body),
                        "content_type": content_type,
                    }
                )
                return 0
            if action == "run-start":
                overrides = {
                    "outer_workers": args.outer_workers,
                    "max_heavy_cpu_jobs": args.max_heavy_cpu_jobs,
                    "speech_enabled": args.speech_enabled,
                    "email_enabled": args.email_enabled,
                }
                overrides = {key: value for key, value in overrides.items() if value is not None}
                _emit(
                    client.json(
                        "POST",
                        "/api/v1/runs",
                        payload={
                            "profile": args.profile,
                            "run_id": args.run_id,
                            "preflight": args.preflight,
                            "overrides": overrides,
                        },
                        timeout=120.0,
                    )
                )
                return 0
            if action == "run-current":
                _emit(client.json("GET", "/api/v1/runs/current"))
                return 0
            if action == "run-stop":
                run_id = args.run_id
                if run_id is None:
                    current = client.json("GET", "/api/v1/runs/current")
                    run_id = current.get("run_id")
                if not run_id:
                    raise ProbabilisticApiCliError("no current run was found")
                _emit(
                    client.json(
                        "POST",
                        f"/api/v1/runs/{run_id}/stop",
                        payload={"force": args.force},
                    )
                )
                return 0
        except ProbabilisticApiCliError as exc:
            _emit({"status": "API_ERROR", "error": str(exc)})
            return 2
    _emit({"status": "NOT_IMPLEMENTED", "action": action})
    return 2

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loto3", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("games", help="print the geometry of every supported game").set_defaults(
        func=_cmd_games
    )

    theory = sub.add_parser("theory", help="exact theoretical bounds")
    theory.add_argument("--game", choices=known_games(), default=None)
    theory.add_argument("--tau", type=int, default=1)
    theory.set_defaults(func=_cmd_theory)

    catalog = sub.add_parser("catalog", help="model registry")
    catalog.add_argument("--counts", action="store_true", help="computed counts only")
    catalog.add_argument("--library", default=None)
    catalog.add_argument("--unpinned", action="store_true", help="only UNPINNED revisions")
    catalog.add_argument("--csv", default=None, help="write the catalog to this CSV path")
    catalog.set_defaults(func=_cmd_catalog)

    revisions = sub.add_parser("revisions", help="validate and apply explicit TSFM commit pins")
    revisions.add_argument("action", choices=["template", "validate", "report", "apply"])
    revisions.add_argument("--manifest", default=None)
    revisions.add_argument("--output", default=None)
    revisions.add_argument("--require-complete", action="store_true")
    revisions.set_defaults(func=_cmd_revisions)

    integrity = sub.add_parser("integrity", help="generate or verify INTEGRITY.json")
    integrity.add_argument("action", choices=["generate", "check"])
    integrity.add_argument("--root", default=".")
    integrity.add_argument("--release", default="3.0.0")
    integrity.add_argument("--allow-untracked", action="store_true")
    integrity.set_defaults(func=_cmd_integrity)

    research = sub.add_parser("research", help="run one instrumented research cycle")
    research.add_argument("--game", choices=known_games(), default="loto7")
    research.add_argument("--input", default=None, help="normalised CSV; omit for synthetic")
    research.add_argument("--synthetic-rows", type=int, default=220)
    research.add_argument("--folds", type=int, default=4)
    research.add_argument("--test-size", type=int, default=10)
    research.add_argument("--min-train-size", type=int, default=80)
    research.add_argument("--holdout-size", type=int, default=20)
    research.add_argument("--tau", type=int, default=1)
    research.add_argument("--alpha", type=float, default=0.05)
    research.add_argument("--n-boot", type=int, default=500)
    research.add_argument(
        "--correction",
        default="romano_wolf",
        choices=["romano_wolf", "holm", "benjamini_hochberg", "none"],
    )
    research.add_argument("--seed", type=int, default=42)
    research.add_argument("--output", default=None)
    research.add_argument("--verbose", action="store_true")
    research.set_defaults(func=_cmd_research)


    probabilistic = sub.add_parser(
        "probabilistic", help="probabilistic-programming model catalog and runner"
    )
    psub = probabilistic.add_subparsers(dest="ppl_action", required=True)

    pcl = psub.add_parser("catalog-list", help="list all 72 probabilistic models")
    pcl.add_argument("--family", default=None)
    pcl.add_argument("--priority", choices=["p0", "p1", "p2"], default=None)
    pcl.set_defaults(func=_cmd_probabilistic)
    pcs = psub.add_parser("catalog-show", help="show one probabilistic model")
    pcs.add_argument("model_id")
    pcs.set_defaults(func=_cmd_probabilistic)

    ppl = psub.add_parser("profiles-list", help="list inference profiles")
    ppl.add_argument("--backend", default=None)
    ppl.set_defaults(func=_cmd_probabilistic)
    pps = psub.add_parser("profiles-show", help="show one inference profile")
    pps.add_argument("profile_id")
    pps.set_defaults(func=_cmd_probabilistic)
    pb = psub.add_parser("backends", help="probe optional backend packages")
    pb.set_defaults(func=_cmd_probabilistic)
    pnc = psub.add_parser("native-coverage", help="show all 72 primary native implementations")
    pnc.set_defaults(func=_cmd_probabilistic)

    pc = psub.add_parser("compatibility", help="check model/game/backend compatibility")
    pc.add_argument("--model-id", required=True)
    pc.add_argument("--game", choices=known_games(), default="numbers3")
    pc.add_argument("--backend", default="builtin")
    pc.add_argument("--profile-id", default=None)
    pc.add_argument("--include-experimental", action="store_true")
    pc.set_defaults(func=_cmd_probabilistic)

    for name in ("validate-config", "plan", "smoke", "run"):
        command = psub.add_parser(name)
        command.add_argument("--config", required=True)
        command.set_defaults(func=_cmd_probabilistic)
    for name in ("status", "diagnose", "compare"):
        command = psub.add_parser(name)
        command.add_argument("--run-dir", required=True)
        command.set_defaults(func=_cmd_probabilistic)

    api_token = psub.add_parser("api-token-create", help="create or rotate the local API token")
    api_token.add_argument("--root", default=".")
    api_token.add_argument("--host", default="127.0.0.1")
    api_token.add_argument("--port", type=int, default=8765)
    api_token.add_argument("--voicevox-url", default="http://127.0.0.1:50021")
    api_token.add_argument("--force", action="store_true")
    api_token.set_defaults(func=_cmd_probabilistic)

    api_serve = psub.add_parser("api-serve", help="serve the authenticated execution API")
    api_serve.add_argument("--root", default=".")
    api_serve.add_argument("--host", default=None)
    api_serve.add_argument("--port", type=int, default=None)
    api_serve.add_argument("--no-access-log", action="store_true")
    api_serve.set_defaults(func=_cmd_probabilistic)

    for name, help_text in (
        ("api-health", "check API health"),
        ("api-profiles", "list allowed API run profiles"),
        ("tts-status", "check the Japanese TTS backend"),
        ("run-current", "show the current API-managed run"),
    ):
        command = psub.add_parser(name, help=help_text)
        command.add_argument("--root", default=".")
        command.add_argument("--base-url", default=None)
        command.set_defaults(func=_cmd_probabilistic)

    tts_play = psub.add_parser("tts-play", help="speak Japanese through VOICEVOX API")
    tts_play.add_argument("--root", default=".")
    tts_play.add_argument("--base-url", default=None)
    tts_play.add_argument("--text", required=True)
    tts_play.add_argument("--speaker", type=int, default=3)
    tts_play.add_argument("--speed-scale", type=float, default=1.15)
    tts_play.set_defaults(func=_cmd_probabilistic)

    tts_synthesize = psub.add_parser("tts-synthesize", help="write VOICEVOX WAV output")
    tts_synthesize.add_argument("--root", default=".")
    tts_synthesize.add_argument("--base-url", default=None)
    tts_synthesize.add_argument("--text", required=True)
    tts_synthesize.add_argument("--output", required=True)
    tts_synthesize.add_argument("--speaker", type=int, default=3)
    tts_synthesize.add_argument("--speed-scale", type=float, default=1.15)
    tts_synthesize.set_defaults(func=_cmd_probabilistic)

    run_start = psub.add_parser("run-start", help="start a permitted probabilistic run profile")
    run_start.add_argument("--root", default=".")
    run_start.add_argument("--base-url", default=None)
    run_start.add_argument(
        "--profile",
        choices=["fast_cpu", "fast_gpu", "standard", "resume_stopped"],
        default="fast_cpu",
    )
    run_start.add_argument("--run-id", default=None)
    run_start.add_argument("--preflight", action=argparse.BooleanOptionalAction, default=True)
    run_start.add_argument("--outer-workers", type=int, default=None)
    run_start.add_argument("--max-heavy-cpu-jobs", type=int, default=None)
    run_start.add_argument("--speech-enabled", action=argparse.BooleanOptionalAction, default=None)
    run_start.add_argument("--email-enabled", action=argparse.BooleanOptionalAction, default=None)
    run_start.set_defaults(func=_cmd_probabilistic)

    run_stop = psub.add_parser("run-stop", help="stop the current or named API-managed run")
    run_stop.add_argument("--root", default=".")
    run_stop.add_argument("--base-url", default=None)
    run_stop.add_argument("--run-id", default=None)
    run_stop.add_argument("--force", action="store_true")
    run_stop.set_defaults(func=_cmd_probabilistic)

    hierarchy = sub.add_parser("hierarchy", help="inspect and test the reconciliation hierarchy")
    hierarchy.add_argument(
        "--game",
        choices=[g for g in known_games() if geometry_for(g).family == "select"],
        default="loto7",
    )
    hierarchy.add_argument("--method", default="wls_struct")
    hierarchy.add_argument("--seed", type=int, default=42)
    hierarchy.set_defaults(func=_cmd_hierarchy)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
