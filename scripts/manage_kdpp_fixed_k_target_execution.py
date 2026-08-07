from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.probabilistic.kdpp_target_execution import (
    prepare_workspace,
    record_cpu_formal,
    record_kdpp_history,
    record_source_handoff,
    verify_control_workspace,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Control the external target-host lifecycle for pp-k-dpp-fixed-k."
    )
    commands = root.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--exporter-repo", type=Path, required=True)
    prepare.add_argument("--exporter-head", required=True)
    prepare.add_argument("--exporter-python", type=Path, required=True)
    prepare.add_argument("--kdpp-repo", type=Path, required=True)
    prepare.add_argument("--kdpp-head", required=True)
    prepare.add_argument("--kdpp-python", type=Path, required=True)
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument(
        "--game",
        choices=("numbers3", "numbers4", "miniloto", "loto6", "loto7"),
        required=True,
    )
    prepare.add_argument("--position", type=int)
    prepare.add_argument("--prediction-length", type=int, choices=(1, 2, 5), required=True)
    prepare.add_argument("--config-sha256", required=True)
    prepare.add_argument("--seed", type=int, default=42)
    prepare.add_argument("--samples-per-horizon", type=int, default=128)
    prepare.add_argument("--rbf-gamma", type=float, default=1.0)
    prepare.add_argument("--quality-pseudocount", type=float, default=0.5)
    prepare.add_argument("--psd-tolerance", type=float, default=1e-10)

    source = commands.add_parser("record-source")
    source.add_argument("--workspace", type=Path, required=True)
    source.add_argument("--handoff", type=Path, required=True)

    history = commands.add_parser("record-history")
    history.add_argument("--workspace", type=Path, required=True)
    history.add_argument("--bundle", type=Path, required=True)
    history.add_argument("--approval", type=Path, required=True)

    runtime = commands.add_parser("record-runtime")
    runtime.add_argument("--workspace", type=Path, required=True)
    runtime.add_argument("--runtime-workspace", type=Path, required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--workspace", type=Path, required=True)
    return root


def _print(payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main() -> int:
    args = parser().parse_args()
    if args.command == "prepare":
        result = prepare_workspace(
            exporter_repo=args.exporter_repo,
            exporter_head=args.exporter_head,
            exporter_python=args.exporter_python,
            kdpp_repo=args.kdpp_repo,
            kdpp_head=args.kdpp_head,
            kdpp_python=args.kdpp_python,
            workspace=args.workspace,
            run_id=args.run_id,
            game=args.game,
            position=args.position,
            prediction_length=args.prediction_length,
            config_sha256=args.config_sha256,
            seed=args.seed,
            samples_per_horizon=args.samples_per_horizon,
            rbf_gamma=args.rbf_gamma,
            quality_pseudocount=args.quality_pseudocount,
            psd_tolerance=args.psd_tolerance,
        )
        _print(result)
        return 0
    if args.command == "record-source":
        _print(record_source_handoff(args.workspace, args.handoff))
        return 0
    if args.command == "record-history":
        _print(record_kdpp_history(args.workspace, args.bundle, args.approval))
        return 0
    if args.command == "record-runtime":
        _print(record_cpu_formal(args.workspace, args.runtime_workspace))
        return 0
    _print(verify_control_workspace(args.workspace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
