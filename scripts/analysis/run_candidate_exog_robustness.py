from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


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

DEFAULT_MODELS = [
    "extra-trees",
    "lightgbm-classifier",
]


def feature_set_hash(columns: list[str]) -> str:
    payload = json.dumps(
        sorted(columns),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
            "permutation_group": None,
        },
        {
            "condition": "frequency_only",
            "feature_group": "historical_frequency",
            "feature_columns": FREQUENCY_FEATURES,
            "permutation_group": None,
        },
        {
            "condition": "gap_only",
            "feature_group": "historical_gap",
            "feature_columns": GAP_FEATURES,
            "permutation_group": None,
        },
        {
            "condition": "full_exogenous",
            "feature_group": "all",
            "feature_columns": all_features,
            "permutation_group": None,
        },
        {
            "condition": "add_frequency",
            "feature_group": "historical_frequency",
            "feature_columns": [
                *IDENTITY_FEATURES,
                *FREQUENCY_FEATURES,
            ],
            "permutation_group": None,
        },
        {
            "condition": "add_gap",
            "feature_group": "historical_gap",
            "feature_columns": [
                *IDENTITY_FEATURES,
                *GAP_FEATURES,
            ],
            "permutation_group": None,
        },
    ]

    for group_name, group_columns in GROUPS.items():
        conditions.append(
            {
                "condition": "drop_group",
                "feature_group": group_name,
                "feature_columns": [
                    column
                    for column in all_features
                    if column not in group_columns
                ],
                "permutation_group": None,
            }
        )
        conditions.append(
            {
                "condition": "block_permutation",
                "feature_group": group_name,
                "feature_columns": all_features,
                "permutation_group": group_name,
            }
        )

    for item in conditions:
        item["feature_set_hash"] = feature_set_hash(
            list(item["feature_columns"])
        )

    return conditions


def block_permute(
    frame: pd.DataFrame,
    *,
    columns: list[str],
    block_size: int,
    seed: int,
) -> pd.DataFrame:
    if block_size <= 0:
        raise ValueError("block_size must be positive")

    output = frame.copy()
    if not columns:
        return output

    row_count = len(output)
    blocks = [
        np.arange(start, min(start + block_size, row_count))
        for start in range(0, row_count, block_size)
    ]

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(blocks))
    source_indexes = np.concatenate([blocks[index] for index in order])

    if len(source_indexes) != row_count:
        raise RuntimeError("block permutation index size mismatch")

    output.loc[:, columns] = (
        output.iloc[source_indexes][columns].to_numpy()
    )
    return output


def constrained_top7(
    candidate_numbers: np.ndarray,
    probabilities: np.ndarray,
) -> np.ndarray:
    order = np.argsort(-probabilities, kind="stable")
    selected = candidate_numbers[order[:7]]
    return np.sort(selected.astype(int))


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
        "mean_hits_at_7": float(
            len(set(actual.tolist()) & set(predicted.tolist()))
        ),
        "brier": float(np.mean((probabilities - labels) ** 2)),
    }


def run_condition(
    *,
    model_id: str,
    train: pd.DataFrame,
    query: pd.DataFrame,
    condition: dict[str, Any],
    seed: int,
    block_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    from loto.models.catalog import get_model_spec
    from loto.models.factory import RuntimeModel

    feature_columns = list(condition["feature_columns"])
    train_data = train[[*feature_columns, "selected"]].copy()
    query_data = query[feature_columns].copy()

    permutation_group = condition.get("permutation_group")
    if permutation_group:
        columns = GROUPS[str(permutation_group)]
        train_data = block_permute(
            train_data,
            columns=columns,
            block_size=block_size,
            seed=seed,
        )
        query_data = block_permute(
            query_data,
            columns=columns,
            block_size=block_size,
            seed=seed + 1,
        )

    model = RuntimeModel(get_model_spec(model_id), seed=seed)
    model.fit_candidate(train_data, target_column="selected")
    result = model.predict_candidate(query_data)

    probabilities = np.asarray(
        result.candidate_probabilities,
        dtype=float,
    )

    if probabilities.shape != (len(query),):
        raise RuntimeError(
            f"{model_id}: expected {len(query)} probabilities, "
            f"got {probabilities.shape}"
        )
    if not np.isfinite(probabilities).all():
        raise RuntimeError(f"{model_id}: non-finite probabilities")

    predicted = constrained_top7(
        query["candidate_number"].to_numpy(dtype=int),
        probabilities,
    )
    return predicted, probabilities


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=(
            "runs/data-acquisition-loto7/features/"
            "candidate_features_v2.parquet"
        ),
    )
    parser.add_argument("--folds", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
    )
    parser.add_argument("--block-size", type=int, default=37)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(
        args.output_dir
        or f"runs/exogenous-robustness-{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input)
    frame = pd.read_parquet(input_path).sort_values(
        ["draw_no", "candidate_number"]
    )

    conditions = build_conditions()
    all_columns = {
        column
        for condition in conditions
        for column in condition["feature_columns"]
    }

    missing = {
        *all_columns,
        "draw_no",
        "candidate_number",
        "selected",
    } - set(frame.columns)
    if missing:
        raise SystemExit(f"Missing columns: {sorted(missing)}")

    draw_numbers = np.sort(frame["draw_no"].unique())
    if not 1 <= args.folds < len(draw_numbers):
        raise SystemExit("folds must be between 1 and draw_count - 1")

    test_draws = draw_numbers[-args.folds :]
    records: list[dict[str, object]] = []

    for fold_index, test_draw in enumerate(test_draws, start=1):
        train = frame[frame["draw_no"] < test_draw].copy()
        query = frame[frame["draw_no"] == test_draw].copy()

        actual = query.loc[
            query["selected"].eq(1),
            "candidate_number",
        ].to_numpy(dtype=int)

        if len(query) != 37 or len(actual) != 7:
            raise RuntimeError(
                f"draw {test_draw}: invalid candidate geometry"
            )

        for model_id in args.models:
            for condition in conditions:
                predicted, probabilities = run_condition(
                    model_id=model_id,
                    train=train,
                    query=query,
                    condition=condition,
                    seed=args.seed,
                    block_size=args.block_size,
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
                        "feature_count": len(
                            condition["feature_columns"]
                        ),
                        "feature_columns": json.dumps(
                            condition["feature_columns"],
                            ensure_ascii=False,
                        ),
                        "feature_set_hash": condition[
                            "feature_set_hash"
                        ],
                        "permutation_group": (
                            condition["permutation_group"] or ""
                        ),
                        "block_size": args.block_size,
                        "actual_numbers": json.dumps(
                            actual.tolist()
                        ),
                        "predicted_numbers": json.dumps(
                            predicted.tolist()
                        ),
                        **metrics,
                    }
                )

        print(
            f"fold={fold_index:03}/{len(test_draws):03} "
            f"draw={test_draw} PASS"
        )

    result = pd.DataFrame(records)
    csv_path = output_dir / "robustness_results.csv"
    parquet_path = output_dir / "robustness_results.parquet"
    result.to_csv(csv_path, index=False)
    result.to_parquet(parquet_path, index=False)

    condition_manifest = output_dir / "condition_manifest.json"
    condition_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "input": str(input_path.resolve()),
                "folds": args.folds,
                "seed": args.seed,
                "models": args.models,
                "block_size": args.block_size,
                "conditions": conditions,
                "rows": int(len(result)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"OUTPUT_DIR={output_dir.resolve()}")
    print(f"ROWS={len(result)}")
    print(f"CSV={csv_path.resolve()}")
    print(f"MANIFEST={condition_manifest.resolve()}")


if __name__ == "__main__":
    main()
