"""CLI for reusable cross-platform parameter-effectiveness suites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters import default_registry
from .contracts import EffectOutcome, ParameterSuiteSpec
from .core import run_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run paired multi-seed forecasting parameter-effectiveness probes "
            "without consuming Holdout or Prospective actuals."
        )
    )
    parser.add_argument("--spec", required=True, type=Path, help="JSON ParameterSuiteSpec")
    parser.add_argument("--output", required=True, type=Path, help="evidence output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    suite = ParameterSuiteSpec.model_validate_json(args.spec.read_text(encoding="utf-8"))
    results = run_suite(suite, default_registry(), args.output)

    print("=" * 96)
    print("PARAMETER EFFECTIVENESS SUITE")
    print("=" * 96)
    print(f"suite={suite.suite_id}")
    print(f"output={args.output}")
    print("holdout_evaluated=False")
    print("prospective_evaluated=False")
    print()

    for result in results:
        fraction = "-" if result.matched_fraction is None else f"{result.matched_fraction:.3f}"
        print(
            f"{result.probe_id}: library={result.library} model={result.model} "
            f"parameter={result.parameter} outcome={result.outcome.value} "
            f"matched={result.pairs_matched}/{result.pairs_eligible} fraction={fraction}"
        )

    print()
    print(json.dumps([item.model_dump(mode="json") for item in results], indent=2))

    blocking = {
        EffectOutcome.FAILED,
        EffectOutcome.UNSUPPORTED,
        EffectOutcome.INCONCLUSIVE,
        EffectOutcome.EXPECTATION_VIOLATED,
    }
    return 2 if any(result.outcome in blocking for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
