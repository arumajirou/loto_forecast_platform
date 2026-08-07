from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .api_coverage_pipeline import run_api_coverage_pipeline
from .contracts import CampaignStage
from .lineage_pipeline import run_stage_with_promotion_and_lineage
from .lineage_verification import verify_run_with_lineage
from .portable_artifact import export_portable_bundle
from .portable_prediction_verification import (
    verify_portable_bundle_with_prediction_lock,
)
from .promotion_gate import GATED_STAGES
from .runner import inventory, load_config, plan, run_stage

# Compatibility patch points retained for existing callers and stacked-PR tests.
# Their implementations now include lineage, prediction-lock, and seal enforcement.
run_stage_with_promotion_gate = run_stage_with_promotion_and_lineage
verify_run_with_coverage = verify_run_with_lineage
verify_portable_bundle = verify_portable_bundle_with_prediction_lock


def _run_id(prefix: str, stage: str) -> str:
    return f"{prefix}-{stage}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _resolve_optional_path(value: Path | None, project: Path) -> Path | None:
    if value is None:
        return None
    return (value if value.is_absolute() else project / value).resolve()


def _resolve_path(value: Path, project: Path) -> Path:
    return (value if value.is_absolute() else project / value).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loto-auto-campaign")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/auto_campaign/campaign.yaml"))
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("inventory", "plan"):
        child = sub.add_parser(command)
        child.add_argument("--output", type=Path, default=None)
    run = sub.add_parser("run")
    run.add_argument(
        "--stage",
        required=True,
        choices=[
            CampaignStage.SMOKE.value,
            CampaignStage.COVERAGE.value,
            CampaignStage.API_COVERAGE.value,
            CampaignStage.HPO.value,
            CampaignStage.VALIDATE_TRIALS.value,
            CampaignStage.OOF.value,
            CampaignStage.HOLDOUT.value,
            CampaignStage.PROSPECTIVE.value,
        ],
    )
    run.add_argument("--output", type=Path, default=None)
    run.add_argument("--source-run", type=Path, default=None)
    run.add_argument(
        "--predecessor-run",
        type=Path,
        default=None,
        help=(
            "immediately preceding verified run; required for holdout (OOF) "
            "and prospective (holdout) lineage"
        ),
    )
    run.add_argument(
        "--coverage-run",
        type=Path,
        default=None,
        help="verified API coverage run required by HPO and later stages",
    )
    run.add_argument(
        "--runtime-run",
        type=Path,
        default=None,
        help="36-model runtime campaign report required when GPU resources are requested",
    )
    run.add_argument("--resume", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    export = sub.add_parser("export-portable")
    export.add_argument("--run", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    portable_verify = sub.add_parser("verify-portable")
    portable_verify.add_argument("--bundle", type=Path, required=True)
    return parser


def _run_portable_command(args: argparse.Namespace, project: Path) -> dict[str, object] | None:
    if args.command == "export-portable":
        try:
            return export_portable_bundle(
                _resolve_path(args.run, project),
                _resolve_path(args.output, project),
            )
        except (OSError, ValueError) as exc:
            return {
                "status": "FAIL",
                "command": args.command,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    if args.command == "verify-portable":
        return verify_portable_bundle(_resolve_path(args.bundle, project))
    return None


def main() -> None:
    args = build_parser().parse_args()
    project = args.project_root.resolve()
    portable_result = _run_portable_command(args, project)
    if portable_result is not None:
        result = portable_result
    else:
        config_path = args.config if args.config.is_absolute() else project / args.config
        config = load_config(config_path)
        data_path = config.data_path if config.data_path.is_absolute() else project / config.data_path
        output_root = (
            config.output_root if config.output_root.is_absolute() else project / config.output_root
        )
        config = config.model_copy(
            update={
                "data_path": data_path.resolve(),
                "output_root": output_root.resolve(),
            }
        )
        if args.command == "verify":
            result = verify_run_with_coverage(args.run.resolve())
        else:
            output = args.output
            if output is None:
                stage = args.command if args.command != "run" else args.stage
                output = config.output_root / _run_id(config.campaign_id_prefix, stage)
            else:
                output = output if output.is_absolute() else project / output
            output = output.resolve()
            if args.command == "inventory":
                result = inventory(project, config, output)
            elif args.command == "plan":
                result = plan(project, config, output)
            else:
                selected_stage = CampaignStage(args.stage)
                source_run = _resolve_optional_path(args.source_run, project)
                predecessor_run = _resolve_optional_path(args.predecessor_run, project)
                coverage_run = _resolve_optional_path(args.coverage_run, project)
                runtime_run = _resolve_optional_path(args.runtime_run, project)
                if selected_stage == CampaignStage.API_COVERAGE:
                    result = run_api_coverage_pipeline(
                        project,
                        config,
                        output,
                        resume=args.resume,
                    )
                elif selected_stage in GATED_STAGES:
                    result = run_stage_with_promotion_gate(
                        runner=run_stage,
                        project_root=project,
                        config=config,
                        run_root=output,
                        target_stage=selected_stage,
                        source_run=source_run,
                        predecessor_run=predecessor_run,
                        coverage_run=coverage_run,
                        runtime_run=runtime_run,
                        resume=args.resume,
                    )
                else:
                    result = run_stage(
                        project,
                        config,
                        output,
                        selected_stage,
                        source_run=source_run,
                        resume=args.resume,
                    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("status") not in {"PASS"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
