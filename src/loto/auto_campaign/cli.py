from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .api_coverage_pipeline import run_api_coverage_pipeline
from .contracts import CampaignStage
from .runner import inventory, load_config, plan, run_stage, verify_run


def _run_id(prefix: str, stage: str) -> str:
    return f"{prefix}-{stage}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


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
    run.add_argument("--resume", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    project = args.project_root.resolve()
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
        result = verify_run(args.run.resolve())
    else:
        output = args.output
        if output is None:
            stage = args.command if args.command != "run" else args.stage
            output = config.output_root / _run_id(config.campaign_id_prefix, stage)
        else:
            output = output if output.is_absolute() else project / output
        if args.command == "inventory":
            result = inventory(project, config, output.resolve())
        elif args.command == "plan":
            result = plan(project, config, output.resolve())
        else:
            selected_stage = CampaignStage(args.stage)
            if selected_stage == CampaignStage.API_COVERAGE:
                result = run_api_coverage_pipeline(
                    project,
                    config,
                    output.resolve(),
                    resume=args.resume,
                )
            else:
                result = run_stage(
                    project,
                    config,
                    output.resolve(),
                    selected_stage,
                    source_run=(
                        None
                        if args.source_run is None
                        else (
                            args.source_run
                            if args.source_run.is_absolute()
                            else project / args.source_run
                        ).resolve()
                    ),
                    resume=args.resume,
                )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("status") not in {"PASS"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
