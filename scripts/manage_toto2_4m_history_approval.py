from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.toto2_campaign.history_handoff import (  # noqa: E402
    APPROVAL_TOKEN,
    ReviewFlags,
    approve_pending,
    create_pending_approval,
)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or approve a Toto 2.0 4M raw-history handoff record"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pending_parser = subparsers.add_parser(
        "create-pending",
        help="Create a non-approved record bound to a verified immutable export",
    )
    _add_common(pending_parser)
    pending_parser.add_argument("--output", type=Path, required=True)

    approve_parser = subparsers.add_parser(
        "approve",
        help="Create an approved record after explicit human review confirmations",
    )
    _add_common(approve_parser)
    approve_parser.add_argument("--pending", type=Path, required=True)
    approve_parser.add_argument("--output", type=Path, required=True)
    approve_parser.add_argument("--reviewer", required=True)
    approve_parser.add_argument("--reviewed-at", required=True)
    approve_parser.add_argument("--approval-token", required=True)
    approve_parser.add_argument("--confirm-source-query", action="store_true")
    approve_parser.add_argument("--confirm-database-snapshot", action="store_true")
    approve_parser.add_argument("--confirm-row-counts", action="store_true")
    approve_parser.add_argument("--confirm-cutoff-dates", action="store_true")
    approve_parser.add_argument("--confirm-position-ranges", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "create-pending":
            approval = create_pending_approval(
                args.export_root,
                args.verification,
                args.output,
            )
        else:
            flags = ReviewFlags(
                source_query_reviewed=args.confirm_source_query,
                database_snapshot_reviewed=args.confirm_database_snapshot,
                row_counts_reviewed=args.confirm_row_counts,
                cutoff_dates_reviewed=args.confirm_cutoff_dates,
                position_ranges_reviewed=args.confirm_position_ranges,
            )
            approval = approve_pending(
                args.export_root,
                args.verification,
                args.pending,
                args.output,
                reviewer=args.reviewer,
                reviewed_at=args.reviewed_at,
                approval_token=args.approval_token,
                review_flags=flags,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"TOTO2_HISTORY_APPROVAL=FAILED\nERROR={type(exc).__name__}: {exc}")
        return 2

    print(f"TOTO2_HISTORY_APPROVAL={approval.status}")
    print(f"OUTPUT={args.output.resolve()}")
    if approval.status == "PENDING":
        print("HUMAN_REVIEW_REQUIRED=true")
        print(f"REQUIRED_APPROVAL_TOKEN={APPROVAL_TOKEN}")
    else:
        print(f"REVIEWER={approval.reviewer}")
        print(f"REVIEWED_AT={approval.reviewed_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
