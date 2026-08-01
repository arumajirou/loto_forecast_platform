from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from loto.models.catalog import get_model_spec
from loto.models.factory import RuntimeModel

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

MODEL_IDS = [
    "logistic",
    "extra-trees",
    "hist-gradient-boosting",
    "lightgbm-classifier",
]


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
        "mean_hits_at_7": float(len(set(actual.tolist()) & set(predicted.tolist()))),
        "brier": float(np.mean((probabilities - labels) ** 2)),
    }


def _build_runtime_model(model_id: str, seed: int) -> RuntimeModel:
    try:
        return RuntimeModel(get_model_spec(model_id), seed=seed)
    except TypeError as exc:
        raise RuntimeError(
            "RuntimeModel API is incompatible with additive batch v1. "
            "Inspect src/loto/models/factory.py before continuing."
        ) from exc


def run_condition(
    *,
    model_id: str,
    train: pd.DataFrame,
    query: pd.DataFrame,
    feature_columns: list[str],
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    train_data = train[[*feature_columns, "selected"]].copy()
    query_data = query[feature_columns].copy()

    model = _build_runtime_model(model_id, seed)

    if not hasattr(model, "fit_candidate") or not hasattr(model, "predict_candidate"):
        raise RuntimeError("RuntimeModel does not expose fit_candidate/predict_candidate.")

    model.fit_candidate(train_data, target_column="selected")
    result = model.predict_candidate(query_data)

    probabilities = getattr(result, "candidate_probabilities", None)
    if probabilities is None:
        raise RuntimeError(f"{model_id} did not return candidate probabilities")

    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.shape != (len(query),):
        raise RuntimeError(
            f"{model_id}: expected {len(query)} probabilities, got {probabilities.shape}"
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
        default=("runs/data-acquisition-loto7/features/candidate_features_v2.parquet"),
    )
    parser.add_argument("--folds", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--models", nargs="+", default=MODEL_IDS)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir or f"runs/exogenous-ablation-candidate-{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input)
    frame = pd.read_parquet(input_path).sort_values(["draw_no", "candidate_number"])

    all_features = [
        *IDENTITY_FEATURES,
        *FREQUENCY_FEATURES,
        *GAP_FEATURES,
    ]

    missing = {
        *all_features,
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

    conditions: list[tuple[str, str, list[str]]] = [
        ("no_exogenous", "none", IDENTITY_FEATURES),
        ("full_exogenous", "all", all_features),
    ]
    for group_name, group_columns in GROUPS.items():
        conditions.append(
            (
                "drop_group",
                group_name,
                [column for column in all_features if column not in group_columns],
            )
        )

    records: list[dict[str, object]] = []

    for fold_index, test_draw in enumerate(test_draws, start=1):
        train = frame[frame["draw_no"] < test_draw].copy()
        query = frame[frame["draw_no"] == test_draw].copy()

        if len(query) != 37:
            raise RuntimeError(f"draw {test_draw}: expected 37 rows, got {len(query)}")

        actual = query.loc[
            query["selected"].eq(1),
            "candidate_number",
        ].to_numpy(dtype=int)

        if len(actual) != 7:
            raise RuntimeError(f"draw {test_draw}: expected 7 selected numbers, got {len(actual)}")

        for model_id in args.models:
            for condition, feature_group, feature_columns in conditions:
                predicted, probabilities = run_condition(
                    model_id=model_id,
                    train=train,
                    query=query,
                    feature_columns=feature_columns,
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
                        "condition": condition,
                        "feature_group": feature_group,
                        "feature_count": len(feature_columns),
                        "feature_columns": json.dumps(
                            feature_columns,
                            ensure_ascii=False,
                        ),
                        "actual_numbers": json.dumps(actual.tolist()),
                        "predicted_numbers": json.dumps(predicted.tolist()),
                        **metrics,
                    }
                )

        print(f"fold={fold_index:03}/{len(test_draws):03} draw={test_draw} PASS")

    result = pd.DataFrame(records)
    csv_path = output_dir / "ablation_results.csv"
    parquet_path = output_dir / "ablation_results.parquet"
    result.to_csv(csv_path, index=False)
    result.to_parquet(parquet_path, index=False)

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "input": str(input_path.resolve()),
        "folds": args.folds,
        "seed": args.seed,
        "models": args.models,
        "conditions": [
            {
                "condition": condition,
                "feature_group": feature_group,
                "feature_columns": columns,
            }
            for condition, feature_group, columns in conditions
        ],
        "rows": len(result),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"OUTPUT_DIR={output_dir.resolve()}")
    print(f"CSV={csv_path.resolve()}")
    print(f"PARQUET={parquet_path.resolve()}")
    print(f"ROWS={len(result)}")


if __name__ == "__main__":
    main()
