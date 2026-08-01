from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from probability_quality import require_candidate_probability_quality

IDENTITY_FEATURES = [
    "candidate_scaled",
    "candidate_is_even",
    "candidate_mod3",
    "candidate_mod10",
    "candidate_is_prime",
]

FREQUENCY_FEATURES = [
    "freq_w5",
    "freq_w10",
    "freq_w20",
    "freq_w30",
    "freq_w50",
    "freq_w100",
    "freq_all",
    "freq_exp",
]

GAP_FEATURES = ["gap_draws"]

GROUPS = {
    "candidate_identity": IDENTITY_FEATURES,
    "historical_frequency": FREQUENCY_FEATURES,
    "historical_gap": GAP_FEATURES,
}

DEFAULT_MODELS = ["extra-trees", "lightgbm-classifier"]


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def feature_set_hash(columns: list[str]) -> str:
    return stable_hash({"columns": sorted(columns)})


def protocol_hash(condition: dict[str, Any], *, seed: int) -> str:
    return stable_hash(
        {
            "condition": condition["condition"],
            "feature_group": condition["feature_group"],
            "feature_columns": sorted(condition["feature_columns"]),
            "transform": condition["transform"],
            "seed": seed,
            "transform_query": True,
            "schema_version": 2,
        }
    )


def build_conditions() -> list[dict[str, Any]]:
    all_features = [
        *IDENTITY_FEATURES,
        *FREQUENCY_FEATURES,
        *GAP_FEATURES,
    ]

    conditions: list[dict[str, Any]] = [
        {
            "condition": "identity_only",
            "feature_group": "candidate_identity",
            "feature_columns": IDENTITY_FEATURES,
            "transform": "none",
        },
        {
            "condition": "frequency_only",
            "feature_group": "historical_frequency",
            "feature_columns": FREQUENCY_FEATURES,
            "transform": "none",
        },
        {
            "condition": "gap_only",
            "feature_group": "historical_gap",
            "feature_columns": GAP_FEATURES,
            "transform": "none",
        },
        {
            "condition": "full_exogenous",
            "feature_group": "all",
            "feature_columns": all_features,
            "transform": "none",
        },
        {
            "condition": "add_frequency",
            "feature_group": "historical_frequency",
            "feature_columns": [
                *IDENTITY_FEATURES,
                *FREQUENCY_FEATURES,
            ],
            "transform": "none",
        },
        {
            "condition": "add_gap",
            "feature_group": "historical_gap",
            "feature_columns": [
                *IDENTITY_FEATURES,
                *GAP_FEATURES,
            ],
            "transform": "none",
        },
    ]

    for group_name, group_columns in GROUPS.items():
        conditions.append(
            {
                "condition": "drop_group",
                "feature_group": group_name,
                "feature_columns": [
                    column for column in all_features if column not in group_columns
                ],
                "transform": "none",
            }
        )

        transform = (
            "within_draw_candidate_permutation"
            if group_name == "candidate_identity"
            else "circular_draw_shift"
        )
        conditions.append(
            {
                "condition": "group_permutation",
                "feature_group": group_name,
                "feature_columns": all_features,
                "transform": transform,
            }
        )

    return conditions


def _within_draw_candidate_permutation(
    frame: pd.DataFrame,
    *,
    columns: list[str],
    seed: int,
) -> pd.DataFrame:
    output = frame.copy()
    rng = np.random.default_rng(seed)

    for _, indexes in output.groupby("draw_no", sort=False).groups.items():
        index_array = np.asarray(list(indexes))
        permutation = rng.permutation(len(index_array))
        output.loc[index_array, columns] = (
            output.loc[index_array, columns].iloc[permutation].to_numpy()
        )

    return output


def _circular_draw_shift(
    frame: pd.DataFrame,
    *,
    columns: list[str],
    shift_draws: int,
    source_pool: pd.DataFrame | None = None,
) -> pd.DataFrame:
    output = frame.copy()
    pool = source_pool.copy() if source_pool is not None else output.copy()
    target_draws = np.sort(output["draw_no"].unique())
    pool_draws = np.sort(pool["draw_no"].unique())

    if len(pool_draws) < 2:
        raise ValueError("circular shift requires at least two source draws")

    normalized_shift = shift_draws % len(pool_draws)
    if normalized_shift == 0:
        normalized_shift = 1

    source_map = {
        target_draw: pool_draws[(index - normalized_shift) % len(pool_draws)]
        for index, target_draw in enumerate(target_draws)
    }

    source = pool[["draw_no", "candidate_number", *columns]].copy()
    selected_sources = []
    for target_draw, source_draw in source_map.items():
        selected = source[source["draw_no"].eq(source_draw)].copy()
        selected["draw_no"] = target_draw
        selected_sources.append(selected)

    shifted_source = pd.concat(
        selected_sources,
        ignore_index=True,
    )

    replacement = output[["draw_no", "candidate_number"]].merge(
        shifted_source,
        on=["draw_no", "candidate_number"],
        how="left",
        validate="one_to_one",
    )

    if replacement[columns].isna().any().any():
        raise RuntimeError("circular shift produced missing values")

    output.loc[:, columns] = replacement[columns].to_numpy()
    return output


def apply_transform(
    frame: pd.DataFrame,
    *,
    condition: dict[str, Any],
    seed: int,
    source_pool: pd.DataFrame | None = None,
) -> pd.DataFrame:
    transform = condition["transform"]
    group = condition["feature_group"]

    if transform == "none":
        return frame.copy()
    if transform == "within_draw_candidate_permutation":
        return _within_draw_candidate_permutation(
            frame,
            columns=GROUPS[group],
            seed=seed,
        )
    if transform == "circular_draw_shift":
        return _circular_draw_shift(
            frame,
            columns=GROUPS[group],
            shift_draws=max(1, seed % 17),
            source_pool=source_pool,
        )

    raise ValueError(f"unknown transform: {transform}")


def transform_changed(
    before: pd.DataFrame,
    after: pd.DataFrame,
    columns: list[str],
) -> bool:
    left = before[columns].reset_index(drop=True)
    right = after[columns].reset_index(drop=True)
    return not left.equals(right)


def constrained_top7(
    candidate_numbers: np.ndarray,
    probabilities: np.ndarray,
) -> np.ndarray:
    order = np.argsort(-probabilities, kind="stable")
    return np.sort(candidate_numbers[order[:7]].astype(int))


def evaluate(
    actual: np.ndarray,
    predicted: np.ndarray,
    probabilities: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float]:
    actual = np.sort(actual.astype(int))
    predicted = np.sort(predicted.astype(int))
    errors = np.abs(predicted - actual)

    return {
        "position_mae": float(np.mean(errors)),
        "position_mse": float(np.mean(errors**2)),
        "element_within_1": float(np.mean(errors <= 1)),
        "row_within_1": float(np.all(errors <= 1)),
        "mean_hits_at_7": float(len(set(actual.tolist()) & set(predicted.tolist()))),
        "brier": float(np.mean((probabilities - labels) ** 2)),
    }


def run_condition(
    *,
    model_id: str,
    train: pd.DataFrame,
    query: pd.DataFrame,
    condition: dict[str, Any],
    seed: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    from loto.models.catalog import get_model_spec
    from loto.models.factory import RuntimeModel

    feature_columns = list(condition["feature_columns"])
    transformed_train = apply_transform(
        train,
        condition=condition,
        seed=seed,
        source_pool=train,
    )
    transformed_query = apply_transform(
        query,
        condition=condition,
        seed=seed + 1,
        source_pool=train,
    )

    transformed_columns = (
        GROUPS[condition["feature_group"]] if condition["transform"] != "none" else []
    )

    if transformed_columns:
        if not transform_changed(
            train,
            transformed_train,
            transformed_columns,
        ):
            raise RuntimeError(
                f"{model_id}: no-op train transformation for {condition['feature_group']}"
            )
        if not transform_changed(
            query,
            transformed_query,
            transformed_columns,
        ):
            raise RuntimeError(
                f"{model_id}: no-op query transformation for {condition['feature_group']}"
            )

    train_data = transformed_train[[*feature_columns, "selected"]].copy()
    query_data = transformed_query[feature_columns].copy()

    model = RuntimeModel(get_model_spec(model_id), seed=seed)
    model.fit_candidate(train_data, target_column="selected")

    if "selected" in model.feature_columns:
        raise RuntimeError(f"{model_id}: selected leaked into fitted feature columns")

    result = model.predict_candidate(query_data)
    probabilities = np.asarray(
        result.candidate_probabilities,
        dtype=float,
    )

    quality = require_candidate_probability_quality(
        probabilities,
        model_id=model_id,
    )

    predicted = constrained_top7(
        query["candidate_number"].to_numpy(dtype=int),
        probabilities,
    )
    return predicted, probabilities, quality.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=("runs/data-acquisition-loto7/features/candidate_features_v2.parquet"),
    )
    parser.add_argument("--folds", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
    )
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir or f"runs/exogenous-robustness-v21-{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_parquet(args.input).sort_values(["draw_no", "candidate_number"])
    conditions = build_conditions()
    test_draws = np.sort(frame["draw_no"].unique())[-args.folds :]

    records: list[dict[str, object]] = []

    for fold_index, test_draw in enumerate(test_draws, start=1):
        train = frame[frame["draw_no"] < test_draw].copy()
        query = frame[frame["draw_no"] == test_draw].copy()
        actual = query.loc[
            query["selected"].eq(1),
            "candidate_number",
        ].to_numpy(dtype=int)

        for model_id in args.models:
            for condition in conditions:
                predicted, probabilities, quality = run_condition(
                    model_id=model_id,
                    train=train,
                    query=query,
                    condition=condition,
                    seed=args.seed,
                )

                metrics = evaluate(
                    actual,
                    predicted,
                    probabilities,
                    query["selected"].to_numpy(dtype=float),
                )

                records.append(
                    {
                        "model_id": model_id,
                        "fold": fold_index,
                        "test_draw_no": int(test_draw),
                        "seed": args.seed,
                        "condition": condition["condition"],
                        "feature_group": condition["feature_group"],
                        "transform": condition["transform"],
                        "feature_set_hash": feature_set_hash(condition["feature_columns"]),
                        "condition_protocol_hash": protocol_hash(
                            condition,
                            seed=args.seed,
                        ),
                        "probability_std": quality["standard_deviation"],
                        "probability_mean": quality["mean"],
                        "probability_unique_count": quality["unique_count"],
                        "actual_numbers": json.dumps(actual.tolist()),
                        "predicted_numbers": json.dumps(predicted.tolist()),
                        **metrics,
                    }
                )

        print(f"fold={fold_index:03}/{len(test_draws):03} draw={test_draw} PASS")

    result = pd.DataFrame(records)
    csv_path = output_dir / "robustness_v21_results.csv"
    parquet_path = output_dir / "robustness_v21_results.parquet"
    result.to_csv(csv_path, index=False)
    result.to_parquet(parquet_path, index=False)

    manifest = {
        "schema_version": 2,
        "input": str(Path(args.input).resolve()),
        "folds": args.folds,
        "seed": args.seed,
        "models": args.models,
        "conditions": conditions,
        "rows": int(len(result)),
    }
    manifest_path = output_dir / "condition_manifest_v21.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"ROWS={len(result)}")
    print(f"CSV={csv_path.resolve()}")
    print(f"MANIFEST={manifest_path.resolve()}")


if __name__ == "__main__":
    main()
