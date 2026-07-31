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
