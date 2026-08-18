#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final

from loto.evaluation.metric_registry import (
    PRIMARY_METRIC_ID,
    REQUIRED_BASELINE_IDS,
    REQUIRED_POINT_METRICS,
)
from loto.game.geometry import known_games
from loto.models.catalog_full import build_catalog
from loto.probabilistic.catalog import (
    build_unified_catalog_rows,
    list_probabilistic_model_specs,
)
from loto.probabilistic.native_registry import list_native_implementations

ROOT: Final = Path(__file__).resolve().parents[2]
UNIFIED_CAMPAIGN_SOURCE: Final = ROOT / "src" / "loto" / "evaluation" / "unified_campaign.py"

EXPECTED_BROAD: Final = 174
EXPECTED_PROBABILISTIC: Final = 76
EXPECTED_UNIFIED: Final = 250
EXPECTED_GAMES: Final = 6
EXPECTED_BROAD_PAIRS: Final = 1044
EXPECTED_INCREMENTAL_PAIRS: Final = 456
EXPECTED_UNIFIED_PAIRS: Final = 1500
EXPECTED_SEEDS: Final = (42, 1729, 20260730)
EXPECTED_METRICS: Final = (
    "hit_at_1",
    "position_hit_at_1",
    "all_positions_hit_at_1",
    "mae",
    "mse",
    "rmse",
)
EXPECTED_BASELINES: Final = (
    "random",
    "fixed",
    "mean",
    "median",
    "last",
    "frequency",
    "statistical_ar1",
)


class ScientificPreflightError(RuntimeError):
    pass


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
            default=str,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(_canonical_json_bytes(payload))
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_unique(name: str, values: list[str]) -> None:
    if len(set(values)) != len(values):
        raise ScientificPreflightError(f"{name} contains duplicate identities")


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _current_scientific_contract() -> tuple[tuple[int, ...], str]:
    """Inspect the current campaign source without importing runtime dependencies."""

    if not UNIFIED_CAMPAIGN_SOURCE.is_file():
        raise ScientificPreflightError(
            f"unified campaign source missing: {UNIFIED_CAMPAIGN_SOURCE}"
        )
    try:
        tree = ast.parse(UNIFIED_CAMPAIGN_SOURCE.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise ScientificPreflightError(f"cannot inspect unified campaign source: {exc}") from exc

    seed_default: tuple[int, ...] | None = None
    selected_entries_calls: set[str] | None = None
    campaign_plan_calls: set[str] | None = None

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "UnifiedCampaignConfig":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "seeds" and item.value is not None:
                        try:
                            raw = ast.literal_eval(item.value)
                        except (ValueError, TypeError) as exc:
                            raise ScientificPreflightError(
                                "UnifiedCampaignConfig.seeds default is not statically readable"
                            ) from exc
                        if not isinstance(raw, tuple) or not all(
                            isinstance(value, int) for value in raw
                        ):
                            raise ScientificPreflightError(
                                "UnifiedCampaignConfig.seeds default is not an integer tuple"
                            )
                        seed_default = tuple(raw)
        elif isinstance(node, ast.FunctionDef) and node.name == "_selected_entries":
            selected_entries_calls = {
                name
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and (name := _call_name(child)) is not None
            }
        elif isinstance(node, ast.FunctionDef) and node.name == "build_campaign_plan":
            campaign_plan_calls = {
                name
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and (name := _call_name(child)) is not None
            }

    if seed_default is None:
        raise ScientificPreflightError("UnifiedCampaignConfig.seeds default not found")
    if selected_entries_calls is None or "build_catalog" not in selected_entries_calls:
        raise ScientificPreflightError(
            "current scientific selector no longer derives entries from build_catalog()"
        )
    if selected_entries_calls & {
        "build_unified_catalog_rows",
        "list_probabilistic_model_specs",
        "list_native_implementations",
    }:
        raise ScientificPreflightError(
            "current scientific selector already references probabilistic/unified identities"
        )
    if campaign_plan_calls is None or "_selected_entries" not in campaign_plan_calls:
        raise ScientificPreflightError(
            "build_campaign_plan no longer derives its matrix from _selected_entries()"
        )
    return seed_default, "broad-only"


def _current_scientific_plan(
    broad_ids: list[str], games: list[str]
) -> tuple[list[dict[str, str]], tuple[int, ...]]:
    current_seeds, surface = _current_scientific_contract()
    if surface != "broad-only":
        raise ScientificPreflightError(f"unexpected current scientific surface: {surface}")
    plan = [
        {"game": game, "candidate_id": model_id}
        for game in games
        for model_id in broad_ids
    ]
    return plan, current_seeds


def collect_preflight_state() -> dict[str, Any]:
    broad = build_catalog()
    probabilistic = list_probabilistic_model_specs()
    unified_rows = build_unified_catalog_rows()
    native = list_native_implementations()
    games = list(known_games())

    broad_ids = [entry.model_id for entry in broad]
    probabilistic_ids = [spec.model_id for spec in probabilistic]
    unified_ids = [str(row["model_id"]) for row in unified_rows]
    native_ids = [item.model_id for item in native]
    current_plan, current_seeds = _current_scientific_plan(broad_ids, games)
    current_scientific_ids = sorted({str(row["candidate_id"]) for row in current_plan})

    _assert_unique("broad catalog", broad_ids)
    _assert_unique("probabilistic catalog", probabilistic_ids)
    _assert_unique("unified catalog", unified_ids)
    _assert_unique("probabilistic native registry", native_ids)

    broad_set = set(broad_ids)
    probabilistic_set = set(probabilistic_ids)
    unified_set = set(unified_ids)
    native_set = set(native_ids)
    current_scientific_set = set(current_scientific_ids)

    collision = sorted(broad_set & probabilistic_set)
    if collision:
        raise ScientificPreflightError(f"Broad/probabilistic identity collision: {collision}")
    if unified_set != broad_set | probabilistic_set:
        raise ScientificPreflightError("unified catalog is not exactly Broad union probabilistic")
    if native_set != probabilistic_set:
        raise ScientificPreflightError("probabilistic/native identity parity failed")
    if current_scientific_set != broad_set:
        raise ScientificPreflightError(
            "current unified_campaign scientific planner no longer matches the Broad catalog"
        )

    counts = {
        "broad_identities": len(broad_ids),
        "probabilistic_identities": len(probabilistic_ids),
        "unified_identities": len(unified_ids),
        "games": len(games),
        "current_scientific_identities": len(current_scientific_ids),
        "current_scientific_pairs": len(current_plan),
        "target_unified_pairs": len(unified_ids) * len(games),
    }
    expected_counts = {
        "broad_identities": EXPECTED_BROAD,
        "probabilistic_identities": EXPECTED_PROBABILISTIC,
        "unified_identities": EXPECTED_UNIFIED,
        "games": EXPECTED_GAMES,
        "current_scientific_identities": EXPECTED_BROAD,
        "current_scientific_pairs": EXPECTED_BROAD_PAIRS,
        "target_unified_pairs": EXPECTED_UNIFIED_PAIRS,
    }
    if counts != expected_counts:
        raise ScientificPreflightError(f"live inventory drift: {counts} != {expected_counts}")

    if tuple(REQUIRED_POINT_METRICS) != EXPECTED_METRICS:
        raise ScientificPreflightError(
            f"metric contract drift: {tuple(REQUIRED_POINT_METRICS)} != {EXPECTED_METRICS}"
        )
    if tuple(REQUIRED_BASELINE_IDS) != EXPECTED_BASELINES:
        raise ScientificPreflightError(
            f"baseline contract drift: {tuple(REQUIRED_BASELINE_IDS)} != {EXPECTED_BASELINES}"
        )
    if PRIMARY_METRIC_ID != "hit_at_1":
        raise ScientificPreflightError(f"primary metric drift: {PRIMARY_METRIC_ID}")
    if tuple(current_seeds) != EXPECTED_SEEDS:
        raise ScientificPreflightError(f"seed contract drift: {tuple(current_seeds)}")

    missing_ids = sorted(unified_set - current_scientific_set)
    if set(missing_ids) != probabilistic_set or len(missing_ids) != EXPECTED_PROBABILISTIC:
        raise ScientificPreflightError("scientific route gap is not exactly the probabilistic catalog")

    target_plan = [
        {
            "game": game,
            "candidate_id": model_id,
            "catalog_source": "probabilistic" if model_id in probabilistic_set else "broad",
            "scientific_route": (
                "ADAPTER_REQUIRED" if model_id in probabilistic_set else "CURRENT_BROAD_ROUTE"
            ),
        }
        for game in games
        for model_id in sorted(unified_ids)
    ]
    if len(target_plan) != EXPECTED_UNIFIED_PAIRS:
        raise ScientificPreflightError("unified scientific plan is not exactly 1,500 rows")
    if len({(row["game"], row["candidate_id"]) for row in target_plan}) != EXPECTED_UNIFIED_PAIRS:
        raise ScientificPreflightError("unified scientific plan contains duplicates")

    gap = {
        "missing_scientific_identities": missing_ids,
        "missing_identity_count": len(missing_ids),
        "missing_model_game_pairs": len(missing_ids) * len(games),
        "expected_missing_model_game_pairs": EXPECTED_INCREMENTAL_PAIRS,
        "required_adapter": "probabilistic-76-development-oof-v1",
        "current_scientific_surface": "broad-only",
        "execution_readiness": "BLOCKED",
        "blocking_reasons": ["PROBABILISTIC_76_OOF_ADAPTER_MISSING"],
    }

    return {
        "schema_version": "taj21-scientific-preflight/v1",
        "status": "PASS",
        "inventory": counts,
        "canonical_games": games,
        "primary_metric": PRIMARY_METRIC_ID,
        "required_metrics": list(REQUIRED_POINT_METRICS),
        "required_baselines": list(REQUIRED_BASELINE_IDS),
        "seed_inventory": list(current_seeds),
        "target_plan": target_plan,
        "route_gap": gap,
        "scientific_boundary": {
            "development_oof": "PLANNED",
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
        "interpretation": (
            "The scientific protocol foundation is valid, but execution readiness remains "
            "blocked until the 76 probabilistic canonical identities receive a development-only "
            "OOF adapter under the same chronological folds, metrics, baselines, seeds, and "
            "prediction-before-actual contract."
        ),
    }


def _write_artifact_manifest(output: Path, paths: list[Path]) -> Path:
    manifest_path = output / "ARTIFACT_MANIFEST.json"
    payload = {
        "schema_version": "artifact-manifest/v1",
        "files": [
            {
                "path": path.relative_to(output).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(paths)
        ],
    }
    _atomic_json(manifest_path, payload)
    return manifest_path


def _write_sha256sums(output: Path) -> Path:
    sums = output / "SHA256SUMS"
    paths = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    lines = [f"{_sha256(path)}  {path.relative_to(output).as_posix()}" for path in paths]
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sums


def build_preflight(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite TAJ-21 preflight output: {output}")
    output.mkdir(parents=True)

    state = collect_preflight_state()
    summary = dict(state)
    target_plan = summary.pop("target_plan")

    summary_path = output / "SCIENTIFIC_PREFLIGHT.json"
    plan_path = output / "UNIFIED_SCIENTIFIC_PLAN.json"
    gap_path = output / "SCIENTIFIC_ROUTE_GAP.json"
    verification_path = output / "VERIFICATION_REPORT.json"

    _atomic_json(summary_path, summary)
    _atomic_json(plan_path, {"schema_version": "taj21-unified-scientific-plan/v1", "rows": target_plan})
    _atomic_json(gap_path, state["route_gap"])
    _atomic_json(
        verification_path,
        {
            "status": "PASS",
            "preflight_status": state["status"],
            "execution_readiness": state["route_gap"]["execution_readiness"],
            "blocking_reasons": state["route_gap"]["blocking_reasons"],
            "checks": {
                "broad_174": True,
                "probabilistic_76": True,
                "unified_250": True,
                "games_6": True,
                "target_pairs_1500": True,
                "current_scientific_pairs_1044": True,
                "missing_pairs_456": True,
                "identity_collision_zero": True,
                "probabilistic_native_parity": True,
                "metrics_contract": True,
                "baseline_contract": True,
                "seed_contract": True,
                "holdout_closed": True,
                "prospective_closed": True,
                "promotion_closed": True,
            },
        },
    )
    manifest = _write_artifact_manifest(
        output,
        [summary_path, plan_path, gap_path, verification_path],
    )
    sums = _write_sha256sums(output)

    return {
        **summary,
        "target_plan_rows": len(target_plan),
        "artifact_manifest_sha256": _sha256(manifest),
        "sha256sums_sha256": _sha256(sums),
        "output": str(output),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-21 unified 250x6 scientific OOF preflight")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_preflight(args.output.resolve())
    except (ScientificPreflightError, FileExistsError) as exc:
        print("TAJ21_SCIENTIFIC_PREFLIGHT=BLOCKED")
        print(f"REASON={exc}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        print("PROMOTION=CLOSED")
        return 20

    gap = result["route_gap"]
    inventory = result["inventory"]
    print("TAJ21_SCIENTIFIC_PREFLIGHT=PASS")
    print(f"UNIFIED_IDENTITIES={inventory['unified_identities']}")
    print(f"GAMES={inventory['games']}")
    print(f"UNIFIED_PAIRS={inventory['target_unified_pairs']}")
    print(f"CURRENT_SCIENTIFIC_IDENTITIES={inventory['current_scientific_identities']}")
    print(f"CURRENT_SCIENTIFIC_PAIRS={inventory['current_scientific_pairs']}")
    print(f"MISSING_SCIENTIFIC_IDENTITIES={gap['missing_identity_count']}")
    print(f"MISSING_SCIENTIFIC_PAIRS={gap['missing_model_game_pairs']}")
    print(f"EXECUTION_READINESS={gap['execution_readiness']}")
    print(f"BLOCKER={gap['blocking_reasons'][0]}")
    print(f"PRIMARY_METRIC={result['primary_metric']}")
    print(f"BASELINES={len(result['required_baselines'])}")
    print("SEEDS=" + ",".join(str(seed) for seed in result["seed_inventory"]))
    print(f"ARTIFACT_MANIFEST_SHA256={result['artifact_manifest_sha256']}")
    print(f"SHA256SUMS_SHA256={result['sha256sums_sha256']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
