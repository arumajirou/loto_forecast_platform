"""``loto-lab`` command line interface.

Subcommands
-----------
``bounds``
    Print the model-independent packing bounds. Runs in seconds and needs no data, so this
    is the cheapest way to see whether a coverage target is worth pursuing at all.
``controls``
    Run the control suite alone, to confirm the leak detector has power before spending a
    search budget.
``run``
    Execute the full state machine to a terminal state.
``verify``
    Re-verify a ledger's hash chain.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loto.combinatorics.bounds import feasibility_bound, feasibility_table
from loto.game.geometry import known_games

__all__ = ["main", "build_parser"]


def _cmd_bounds(args: argparse.Namespace) -> int:
    games = [args.game] if args.game else known_games()
    coverages = [float(c) for c in args.coverage]
    if args.json:
        rows = feasibility_table(
            games, coverages=coverages, tolerance=args.tolerance, mean_samples=args.mean_samples
        )
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    header = (
        f"{'game':10s} {'|Omega|':>12s} {'maxN':>7s} {'meanN':>9s} "
        f"{'c':>5s} {'min tickets':>12s} {'cost JPY':>12s}"
    )
    print(header)
    print("-" * len(header))
    for game in games:
        for coverage in coverages:
            bound = feasibility_bound(
                game,
                target_coverage=coverage,
                tolerance=args.tolerance,
                mean_samples=args.mean_samples,
            )
            cost = "" if bound.lower_bound_cost_jpy is None else f"{bound.lower_bound_cost_jpy:,}"
            print(
                f"{bound.game:10s} {bound.outcome_space:>12,} {bound.max_neighbourhood:>7,} "
                f"{bound.mean_neighbourhood:>9.1f} {coverage:>5.2f} "
                f"{bound.lower_bound_tickets:>12,} {cost:>12s}"
            )
    print()
    print(
        "min tickets is a packing bound: it assumes zero overlap between ticket "
        "neighbourhoods, so it is optimistic and model-independent. No forecasting method "
        "can beat it. Coverage at tolerance >= 1 is not a prize condition, so cost is the "
        "purchase price of the pool, not a wager with a matching return."
    )
    return 0


def _cmd_controls(args: argparse.Namespace) -> int:
    import numpy as np

    from loto.combinatorics.designs import reference_pool
    from loto.kpi_lab.negative_controls import run_control_suite
    from loto.kpi_lab.runner import load_draws

    draws = load_draws(args.draws, args.game)
    tickets, _ = reference_pool(
        args.game, n_tickets=args.tickets, tolerance=args.tolerance
    )

    def builder(target_draws, n_tickets, seed):
        from loto.kpi_lab.arms import build_model_arm

        n = target_draws.shape[0]
        cut = max(10, int(n * 0.6))
        arm = build_model_arm(
            game=args.game,
            n_tickets=n_tickets,
            history=target_draws[:cut],
            calibration_draws=target_draws[cut:],
            sealed_draws=target_draws[cut:],
            parameters={"point_method": "mean"},
            tolerance=args.tolerance,
            seed=seed,
            n_monte_carlo=200,
        )
        return list(arm.tickets)

    report = run_control_suite(
        game=args.game,
        draws=np.asarray(draws),
        model_pool_builder=builder,
        reference_pool=list(tickets),
        n_tickets=args.tickets,
        tolerance=args.tolerance,
        max_false_positive_rate=args.max_fp_rate,
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 2 if report.suspend else 0


def _cmd_run(args: argparse.Namespace) -> int:
    from loto.kpi_lab.runner import run_lab_from_config

    payload = run_lab_from_config(args.config, draws_path=args.draws)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"terminal_state : {payload['terminal_state']}")
        print(f"reason         : {payload['reason']}")
        print(f"experiments    : {payload['n_experiments']}")
        print(f"ledger         : {payload['ledger_path']}")
        print(f"ledger valid   : {payload['ledger_integrity']['valid']}")
        print(f"claims skill   : {payload['claims_model_skill']}")
    # Exit codes distinguish the terminal states so a scheduler can react without parsing
    # prose. Note that a zero exit does NOT mean the model worked.
    return {
        "KPI_MET_VERIFIED": 0,
        "KPI_MET_NO_MODEL_VALUE": 0,
        "KPI_MET_DEGENERATE": 0,
        "BUDGET_EXHAUSTED": 0,
        "KPI_INFEASIBLE": 3,
        "LEAK_DETECTED_SUSPENDED": 4,
        "PROTOCOL_VIOLATION": 5,
    }.get(str(payload["terminal_state"]), 1)


def _cmd_verify(args: argparse.Namespace) -> int:
    from loto.kpi_lab.ledger import ExperimentLedger

    ledger = ExperimentLedger(args.ledger, session_id="verify-only")
    integrity = ledger.verify()
    print(json.dumps(integrity.to_dict(), indent=2, ensure_ascii=False))
    return 0 if integrity.valid else 6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-lab",
        description=(
            "Coverage KPI laboratory. Establishes the model-independent lower bound first, "
            "then tests whether any model beats a data-free covering pool."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bounds = sub.add_parser("bounds", help="print model-independent packing bounds")
    bounds.add_argument("--game", choices=known_games(), default=None)
    bounds.add_argument("--coverage", nargs="+", default=["0.5", "0.7", "0.9", "0.95"])
    bounds.add_argument("--tolerance", type=int, default=1)
    bounds.add_argument("--mean-samples", type=int, default=800, dest="mean_samples")
    bounds.add_argument("--json", action="store_true")
    bounds.set_defaults(func=_cmd_bounds)

    controls = sub.add_parser("controls", help="run the control suite only")
    controls.add_argument("--game", choices=known_games(), required=True)
    controls.add_argument("--draws", required=True, help="CSV of draw history")
    controls.add_argument("--tickets", type=int, default=500)
    controls.add_argument("--tolerance", type=int, default=1)
    controls.add_argument("--max-fp-rate", type=float, default=0.05, dest="max_fp_rate")
    controls.set_defaults(func=_cmd_controls)

    run = sub.add_parser("run", help="run the lab to a terminal state")
    run.add_argument("--config", required=True, help="YAML lab config")
    run.add_argument("--draws", default=None, help="override data.draws_path")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=_cmd_run)

    verify = sub.add_parser("verify", help="verify a ledger hash chain")
    verify.add_argument("--ledger", required=True, type=Path)
    verify.set_defaults(func=_cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
