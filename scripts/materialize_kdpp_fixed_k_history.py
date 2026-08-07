from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.probabilistic.kdpp_certification_gate import APPROVAL_TOKEN, validate_history_bundle
from loto.probabilistic.kdpp_history_materializer import (
    approve_history_bundle,
    create_pending_approval,
    materialize_kdpp_history,
)

_CONFIRMATIONS = (
    "source_read_only_confirmed",
    "train_only_confirmed",
    "draw_order_confirmed",
    "row_count_confirmed",
    "game_geometry_confirmed",
    "cutoff_confirmed",
    "no_future_actuals_confirmed",
    "no_holdout_confirmed",
    "no_prospective_confirmed",
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Materialize and approve Train-only history for pp-k-dpp-fixed-k."
    )
    commands = root.add_subparsers(dest="command", required=True)

    materialize = commands.add_parser("materialize")
    materialize.add_argument("--source-handoff", type=Path, required=True)
    materialize.add_argument("--output-dir", type=Path, required=True)
    materialize.add_argument(
        "--game",
        choices=("numbers3", "numbers4", "miniloto", "loto6", "loto7"),
        required=True,
    )
    materialize.add_argument("--position", type=int)

    pending = commands.add_parser("pending")
    pending.add_argument("--bundle", type=Path, required=True)
    pending.add_argument("--output", type=Path, required=True)

    approve = commands.add_parser("approve")
    approve.add_argument("--bundle", type=Path, required=True)
    approve.add_argument("--pending", type=Path, required=True)
    approve.add_argument("--output", type=Path, required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reviewed-at-utc", required=True)
    approve.add_argument("--approval-token", choices=(APPROVAL_TOKEN,), required=True)
    for name in _CONFIRMATIONS:
        option = f"--confirm-{name.removesuffix('_confirmed').replace('_', '-')}"
        approve.add_argument(option, action="store_true")

    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--approval", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "materialize":
        result = materialize_kdpp_history(
            args.source_handoff,
            args.output_dir,
            game=args.game,
            position=args.position,
        )
        print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
        return 0
    if args.command == "pending":
        result = create_pending_approval(args.bundle, args.output)
        print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
        return 0
    if args.command == "approve":
        confirmations = {
            name: bool(getattr(args, f"confirm_{name.removesuffix('_confirmed')}"))
            for name in _CONFIRMATIONS
        }
        result = approve_history_bundle(
            args.bundle,
            args.pending,
            args.output,
            reviewer=args.reviewer,
            reviewed_at_utc=args.reviewed_at_utc,
            approval_token=args.approval_token,
            confirmations=confirmations,
        )
        print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
        return 0
    manifest, approval, item_ids = validate_history_bundle(args.bundle, args.approval)
    print(
        json.dumps(
            {
                "status": "VERIFIED_APPROVED_KDPP_HISTORY",
                "game": manifest.game,
                "position": manifest.position,
                "row_count": manifest.row_count,
                "reviewer": approval.reviewer,
                "item_count": len(item_ids),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
