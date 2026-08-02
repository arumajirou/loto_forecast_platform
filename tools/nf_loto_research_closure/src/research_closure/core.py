from __future__ import annotations

import hashlib
import json
import pickle
import platform
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

STAGE_PATTERNS: dict[str, str] = {
    "f0c": "stage-f0c-final-rolling-audit-*",
    "f1a": "stage-f1a-numpyro-categorical-*",
    "f1b": "stage-f1b-dynamic-categorical-*",
    "f2a": "stage-f2a-ordinal-catboost-*",
    "f2b": "stage-f2b-repeated-logistic-*",
    "constant_audit": "train-only-constant-audit-*",
}

REQUIRED_STAGES = ("f0c", "f1a", "f1b", "f2a", "f2b")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def git_value(project_root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def load_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported dataset format: {path.suffix}")

    missing = {"ds", "y"} - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset columns missing: {sorted(missing)}")

    result = frame[["ds", "y"]].copy()
    result["ds"] = pd.to_datetime(result["ds"], errors="raise")
    result["y"] = pd.to_numeric(result["y"], errors="raise").astype(int)
    result = (
        result.sort_values("ds").drop_duplicates(subset=["ds"], keep="last").reset_index(drop=True)
    )
    if not result["ds"].is_unique:
        raise ValueError("Duplicate ds values remain")
    if not result["ds"].is_monotonic_increasing:
        raise ValueError("Dataset is not time ordered")
    if not result["y"].between(0, 9).all():
        raise ValueError("Target y must be an integer from 0 through 9")
    return result


def latest_successful_run(artifact_root: Path, pattern: str) -> Path | None:
    candidates: list[tuple[float, Path]] = []
    for run_dir in artifact_root.glob(pattern):
        summary_path = run_dir / "summary.json"
        if not summary_path.is_file():
            continue
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") != "PASS":
            continue
        candidates.append((summary_path.stat().st_mtime, run_dir))
    return max(candidates, default=(0.0, None), key=lambda item: item[0])[1]


def discover_stage_runs(
    artifact_root: Path,
    require_all: bool = True,
) -> dict[str, Path]:
    runs: dict[str, Path] = {}
    for stage, pattern in STAGE_PATTERNS.items():
        run = latest_successful_run(artifact_root, pattern)
        if run is not None:
            runs[stage] = run
    missing = sorted(set(REQUIRED_STAGES) - set(runs))
    if missing and require_all:
        raise FileNotFoundError("Missing successful stage runs: " + ", ".join(missing))
    return runs


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    return None if value is None else float(value)


def _write_markdown(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _manifest(root: Path, exclude: Iterable[str] = ()) -> list[dict[str, Any]]:
    excluded = set(exclude)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in excluded:
            continue
        rows.append(
            {
                "relative_path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def write_sha256sums(root: Path) -> Path:
    target = root / "SHA256SUMS"
    rows = _manifest(root, exclude={"SHA256SUMS"})
    target.write_text(
        "".join(f"{row['sha256']}  {row['relative_path']}\n" for row in rows),
        encoding="utf-8",
    )
    return target


def verify_sha256sums(root: Path) -> list[str]:
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        raise FileNotFoundError(sums)
    failures: list[str] = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file() or sha256_file(path) != expected:
            failures.append(relative)
    return failures


@dataclass(frozen=True)
class ClosureResult:
    output_dir: str
    data_sha256: str
    source_runs: dict[str, str]
    formal_pass_models: list[str]
    production_model: str | None
    decision: str


def create_closure_package(
    project_root: Path,
    artifact_root: Path,
    data_path: Path,
    output_dir: Path,
    require_all: bool = True,
) -> ClosureResult:
    project_root = project_root.resolve()
    artifact_root = artifact_root.resolve()
    data_path = data_path.resolve()
    output_dir = output_dir.resolve()

    dataset = load_dataset(data_path)
    data_hash = sha256_file(data_path)
    runs = discover_stage_runs(artifact_root, require_all=require_all)

    documents = output_dir / "documents"
    evidence = output_dir / "evidence"
    registry = output_dir / "registry"
    manifests = output_dir / "manifests"
    for directory in (documents, evidence, registry, manifests):
        directory.mkdir(parents=True, exist_ok=True)

    summaries: dict[str, dict[str, Any]] = {}
    evidence_rows: list[dict[str, Any]] = []
    preferred = {
        "summary.json",
        "environment.json",
        "aggregate_ranking.csv",
        "aggregate_ranking.parquet",
        "ranking.csv",
        "ranking.parquet",
        "probability_metrics.csv",
        "split_average_metrics.csv",
        "seed_split_metrics.csv",
        "paired_block_bootstrap.csv",
        "feature_stability.csv",
        "formal_pass_models.csv",
        "SHA256SUMS",
    }
    for stage, run in runs.items():
        summaries[stage] = _read_json(run / "summary.json")
        destination = evidence / stage / run.name
        destination.mkdir(parents=True, exist_ok=True)
        for source in sorted(run.iterdir()):
            if not source.is_file() or source.name not in preferred:
                continue
            target = destination / source.name
            shutil.copy2(source, target)
            evidence_rows.append(
                {
                    "stage": stage,
                    "source": str(source),
                    "relative_path": str(target.relative_to(output_dir)),
                    "size_bytes": target.stat().st_size,
                    "sha256": sha256_file(target),
                }
            )

    f0c = summaries.get("f0c", {})
    f1a = summaries.get("f1a", {})
    f1b = summaries.get("f1b", {})
    f2a = summaries.get("f2a", {})
    f2b = summaries.get("f2b", {})

    closure = {
        "schema_version": "1.0",
        "created_at_utc": utc_now(),
        "dataset": {
            "path": str(data_path),
            "sha256": data_hash,
            "rows": len(dataset),
            "minimum_ds": str(dataset["ds"].min()),
            "maximum_ds": str(dataset["ds"].max()),
            "target_minimum": int(dataset["y"].min()),
            "target_maximum": int(dataset["y"].max()),
        },
        "primary_metric": "Hit@±1",
        "research_targets": {
            "hit_at_pm1_90": {"status": "CLOSED", "supported": False},
            "hit_at_pm1_35": {"status": "NOT_ACHIEVED", "supported": False},
        },
        "formal_production_model": None,
        "prospective_promotion": False,
        "formal_pass_models": [],
        "shadow_models": [
            "train_only_constant",
            "rolling_dirichlet_w20_a5",
            "tree_depth4",
            "multinomial_logistic",
        ],
        "minimum_prospective_rows": 100,
        "prediction_lock_required": True,
        "prediction_lock_algorithm": "SHA-256",
        "model_search_status": "FROZEN_UNTIL_NEW_INFORMATION",
        "source_runs": {key: str(value) for key, value in runs.items()},
    }
    (registry / "RESEARCH_CLOSURE_STATUS.json").write_text(
        json.dumps(closure, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    model_rows = [
        {
            "model_id": "numbers3-n1-train-only-constant",
            "family": "train_only_constant",
            "role": "reference_baseline",
            "formal_status": "BASELINE_ONLY",
        },
        {
            "model_id": "numbers3-n1-dirichlet-w20-a5",
            "family": "rolling_dirichlet",
            "role": "shadow_baseline",
            "formal_status": "BASELINE_ONLY",
        },
        {
            "model_id": "numbers3-n1-tree-depth4",
            "family": "decision_tree_classifier",
            "role": "shadow_candidate",
            "formal_status": "REJECTED",
        },
        {
            "model_id": "numbers3-n1-multinomial-logistic",
            "family": "multinomial_logistic",
            "role": "shadow_candidate",
            "formal_status": "REJECTED",
        },
    ]
    pd.DataFrame(model_rows).to_csv(registry / "MODEL_REGISTRY.csv", index=False)
    (registry / "MODEL_REGISTRY.json").write_text(
        json.dumps(model_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    experiment_rows = [
        {
            "stage": "F0c",
            "method": "tree_depth4",
            "evaluation": "repeated temporal rolling audit",
            "hit_at_pm1": _safe_float(f0c, "best_mean_hit"),
            "decision": f0c.get("decision", "UNKNOWN"),
        },
        {
            "stage": "F1a",
            "method": f1a.get("top_method", "numpyro_multinomial"),
            "evaluation": "single holdout smoke",
            "hit_at_pm1": _safe_float(f1a, "top_hit_within_1"),
            "decision": "REJECT_STATIC_BAYESIAN",
        },
        {
            "stage": "F1b",
            "method": "dynamic_grw_hit_optimal",
            "evaluation": "single holdout smoke",
            "hit_at_pm1": _safe_float(f1b, "dynamic_hit"),
            "decision": "REJECT_DYNAMIC_GRW",
        },
        {
            "stage": "F2a",
            "method": f2a.get("top_method", "multinomial_logistic"),
            "evaluation": "single holdout smoke",
            "hit_at_pm1": _safe_float(f2a, "top_hit_within_1"),
            "decision": "CONDITIONAL_ONLY",
        },
        {
            "stage": "F2b",
            "method": f2b.get("best_method", "multinomial_logistic"),
            "evaluation": "5 temporal splits x multiple seeds",
            "hit_at_pm1": _safe_float(f2b, "best_mean_hit"),
            "decision": f2b.get("decision", "UNKNOWN"),
        },
    ]
    pd.DataFrame(experiment_rows).to_csv(documents / "EXPERIMENT_SUMMARY.csv", index=False)

    _write_markdown(
        output_dir / "README.md",
        """
# Numbers3 N1 Research Closure Package

現在のデータ・特徴量・評価条件では正式合格モデルはありません。
このパッケージは研究終了判定、証跡、モデル台帳、SHA-256検証を保存します。

- `documents/VERIFICATION_REPORT.md`
- `registry/RESEARCH_CLOSURE_STATUS.json`
- `registry/MODEL_REGISTRY.csv`
- `manifests/ARTIFACT_MANIFEST.json`
- `SHA256SUMS`
""",
    )
    _write_markdown(
        documents / "REQUIREMENTS.md",
        """
# REQUIREMENTS

- 最優先指標はHit@±1。
- Train/Calibration/Holdout/Prospectiveを時間順に分離する。
- 特徴量選択、Scaler、調整はTrain系区間内だけで行う。
- 複数seedの平均・分散・最悪値を保存する。
- 固定値、平均、中央値、直近値、頻度、統計モデルと比較する。
- 実測判明前に予測JSONをSHA-256で固定する。
- Rawデータを上書きしない。
""",
    )
    _write_markdown(
        documents / "SPECIFICATION.md",
        """
# SPECIFICATION

- Hit@±1 90%: CLOSED
- Hit@±1 35%: NOT ACHIEVED
- Production model: NONE
- Formal prospective model: NONE
- Shadow candidates: constant, Dirichlet, tree depth 4, multinomial logistic
- Minimum prospective observations before reassessment: 100
""",
    )
    _write_markdown(
        documents / "ARCHITECTURE.md",
        """
# ARCHITECTURE

```text
Immutable raw data -> validation -> past-only features
 -> train-only transform/model -> temporal evaluation
 -> prediction lock (SHA-256) -> prospective registry
```
""",
    )
    _write_markdown(
        documents / "DATA_CONTRACT.md",
        f"""
# DATA CONTRACT

- Required columns: `ds`, `y`
- `ds`: unique chronological datetime
- `y`: integer 0..9
- Rows: {len(dataset)}
- Data SHA-256: `{data_hash}`
- Raw data is immutable.
""",
    )
    _write_markdown(
        documents / "TEST_PLAN.md",
        """
# TEST PLAN

Dataset order/duplicates/range, past-only feature shift, split boundaries,
finite predictions, shape, prediction collapse, repeated seeds, paired baseline
comparison, artifact SHA-256, and prospective cutoff are mandatory.
""",
    )
    _write_markdown(
        documents / "VERIFICATION_REPORT.md",
        f"""
# VERIFICATION REPORT

## Conclusion

正式合格モデルは0件です。Production modelは登録しません。
90%目標は終了、35%目標は未達として記録します。

## Dataset

- Rows: {len(dataset)}
- Range: {dataset["ds"].min()} to {dataset["ds"].max()}
- SHA-256: `{data_hash}`

## Evidence summary

- F0c: `{f0c.get("decision", "UNKNOWN")}`, best mean Hit@±1={f0c.get("best_mean_hit")}
- F1a: Hit@±1={f1a.get("top_hit_within_1")}
- F1b: Hit@±1={f1b.get("dynamic_hit")}, continue={f1b.get("continue_to_f1c")}
- F2a: best={f2a.get("top_method")}, Hit@±1={f2a.get("top_hit_within_1")}
- F2b: `{f2b.get("decision", "UNKNOWN")}`, mean Hit@±1={f2b.get("best_mean_hit")}

単一Holdoutの結果だけでは成功を宣言しません。
""",
    )
    _write_markdown(
        documents / "RUNBOOK.md",
        """
# RUNBOOK

1. RawデータHashと最新実測日時を記録する。
2. 実測未知の予測対象日時を指定する。
3. `shadow-lock`で4方式の予測を作る。
4. lock JSONとSHA-256を保存する。
5. 実測判明後に別記録として評価する。
6. 100件未満では正式昇格しない。
""",
    )
    _write_markdown(
        documents / "HANDOFF.md",
        """
# HANDOFF

現在は研究停止・Shadow monitoring状態です。
単一Holdoutの高値を正式精度として使用しないでください。
Shadow候補をProduction modelと表示しないでください。
""",
    )
    _write_markdown(
        documents / "CHANGELOG.md",
        f"""
# CHANGELOG

## {datetime.now(UTC).date()}

- Research closure package created.
- Production model set to none.
- Four shadow candidates retained.
- Evidence and SHA-256 manifests generated.
""",
    )

    pd.DataFrame(evidence_rows).to_csv(manifests / "EVIDENCE_SOURCE_MANIFEST.csv", index=False)
    environment = {
        "created_at_utc": utc_now(),
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "git_commit": git_value(project_root, "rev-parse", "HEAD"),
        "git_status": git_value(project_root, "status", "--short"),
    }
    (manifests / "ENVIRONMENT.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    initial_manifest = _manifest(
        output_dir,
        exclude={"SHA256SUMS", "ARTIFACT_MANIFEST.csv", "ARTIFACT_MANIFEST.json"},
    )
    pd.DataFrame(initial_manifest).to_csv(manifests / "ARTIFACT_MANIFEST.csv", index=False)
    (manifests / "ARTIFACT_MANIFEST.json").write_text(
        json.dumps(initial_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_sha256sums(output_dir)

    return ClosureResult(
        output_dir=str(output_dir),
        data_sha256=data_hash,
        source_runs={key: str(value) for key, value in runs.items()},
        formal_pass_models=[],
        production_model=None,
        decision="RESEARCH_CLOSED_NO_FORMAL_MODEL",
    )


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    shifted = frame["y"].shift(1)
    parts: dict[str, Any] = {
        "ds": frame["ds"],
        "y": frame["y"],
        "weekday": frame["ds"].dt.weekday,
        "month": frame["ds"].dt.month,
        "day": frame["ds"].dt.day,
    }
    for lag in range(1, 101):
        parts[f"lag_{lag}"] = frame["y"].shift(lag)
    for window in (5, 10, 20, 50, 100, 200):
        rolling = shifted.rolling(window=window, min_periods=window)
        parts[f"mean_{window}"] = rolling.mean()
        parts[f"median_{window}"] = rolling.median()
        parts[f"std_{window}"] = rolling.std()
        parts[f"min_{window}"] = rolling.min()
        parts[f"max_{window}"] = rolling.max()
        for digit in range(10):
            parts[f"freq_{digit}_{window}"] = (
                shifted.eq(digit).rolling(window, min_periods=window).mean()
            )
    result = pd.DataFrame(parts)
    feature_columns = [column for column in result.columns if column not in {"ds", "y"}]
    return result.dropna(subset=feature_columns).reset_index(drop=True)


def select_best_constant(history: np.ndarray) -> int:
    candidates: list[tuple[float, float, float, int]] = []
    for digit in range(10):
        error = np.abs(history - digit)
        candidates.append(
            (-float(np.mean(error <= 1)), float(np.mean(error)), float(np.mean(error**2)), digit)
        )
    candidates.sort()
    return candidates[0][3]


def hit_optimal(probability: np.ndarray) -> tuple[int, float]:
    scores = []
    for candidate in range(10):
        low, high = max(0, candidate - 1), min(9, candidate + 1)
        scores.append(float(probability[low : high + 1].sum()))
    prediction = int(np.argmax(scores))
    return prediction, scores[prediction]


def dirichlet_prediction(
    history: np.ndarray, window: int = 20, alpha: float = 5.0
) -> tuple[int, float]:
    values = history[-min(window, len(history)) :]
    counts: np.ndarray = np.bincount(
        values,
        minlength=10,
    ).astype(float)
    probability = (counts + alpha) / (counts.sum() + 10 * alpha)
    return hit_optimal(probability)


def _pickle_sha256(value: Any) -> str:
    return hashlib.sha256(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)).hexdigest()


def train_shadow_predictions(
    dataset: pd.DataFrame,
    target_ds: pd.Timestamp,
    seed: int = 20260802,
    top_features: int = 30,
) -> dict[str, dict[str, Any]]:
    # Add an unlabeled future row. Its features are constructed only from
    # observations at or before dataset cutoff, so the forecast row is real
    # prospective input rather than the final known target replayed as future.
    future_source = pd.concat(
        [
            dataset.copy(),
            pd.DataFrame({"ds": [target_ds], "y": [np.nan]}),
        ],
        ignore_index=True,
    )
    feature_frame = build_features(future_source)
    if len(feature_frame) < 501:
        raise ValueError("At least 700 raw rows are recommended for the default features")

    next_features = feature_frame.loc[feature_frame["ds"].eq(target_ds)].copy()
    if len(next_features) != 1:
        raise RuntimeError("Exactly one future feature row must be generated")

    train = feature_frame.loc[feature_frame["ds"].lt(target_ds)].dropna(subset=["y"]).copy()
    feature_columns = [column for column in feature_frame.columns if column not in {"ds", "y"}]
    y_train = train["y"].to_numpy(dtype=int)

    if train["ds"].max() != dataset["ds"].max():
        raise RuntimeError("Training cutoff does not match dataset cutoff")
    if not train["ds"].max() < next_features["ds"].iloc[0]:
        raise RuntimeError("Future feature row is not after training cutoff")

    mi = mutual_info_classif(
        train[feature_columns].to_numpy(dtype=float),
        y_train,
        random_state=seed,
    )
    selected = (
        pd.DataFrame({"feature": feature_columns, "mi": mi})
        .sort_values(["mi", "feature"], ascending=[False, True])
        .head(top_features)["feature"]
        .tolist()
    )
    selected_features_sha256 = sha256_json(selected)

    history = dataset["y"].to_numpy(dtype=int)
    constant = select_best_constant(history)
    dirichlet, dirichlet_conf = dirichlet_prediction(history)

    tree_config = {
        "class": "sklearn.tree.DecisionTreeClassifier",
        "max_depth": 4,
        "random_state": seed,
        "decision_rule": "argmax P(|Y-candidate|<=1)",
    }
    tree = DecisionTreeClassifier(max_depth=4, random_state=seed)
    tree.fit(train[selected], y_train)
    tree_probability: np.ndarray = np.zeros(
        10,
        dtype=float,
    )
    tree_raw_probability = tree.predict_proba(next_features[selected])[0]
    for index, cls in enumerate(tree.classes_):
        tree_probability[int(cls)] = tree_raw_probability[index]
    tree_pred, tree_conf = hit_optimal(tree_probability)

    logistic_config = {
        "class": "sklearn.linear_model.LogisticRegression",
        "max_iter": 5000,
        "C": 0.10,
        "solver": "lbfgs",
        "random_state": seed,
        "scaler": "sklearn.preprocessing.StandardScaler",
        "decision_rule": "argmax P(|Y-candidate|<=1)",
    }
    scaler = StandardScaler()
    x_train = scaler.fit_transform(train[selected])
    x_next = scaler.transform(next_features[selected])
    logistic = LogisticRegression(
        max_iter=5000,
        C=0.10,
        solver="lbfgs",
        random_state=seed,
    )
    logistic.fit(x_train, y_train)
    logistic_probability: np.ndarray = np.zeros(
        10,
        dtype=float,
    )
    logistic_raw_probability = logistic.predict_proba(x_next)[0]
    for index, cls in enumerate(logistic.classes_):
        logistic_probability[int(cls)] = logistic_raw_probability[index]
    logistic_pred, logistic_conf = hit_optimal(logistic_probability)

    common = {
        "training_rows": int(len(train)),
        "training_cutoff_ds": str(train["ds"].max()),
        "forecast_feature_ds": str(next_features["ds"].iloc[0]),
        "selected_features_sha256": selected_features_sha256,
    }
    return {
        "train_only_constant": {
            **common,
            "model_id": "numbers3-n1-train-only-constant",
            "model_family": "train_only_constant",
            "configuration": {
                "selection_metric": "Hit@±1",
                "tie_breakers": ["MAE", "MSE", "digit"],
            },
            "prediction": constant,
            "confidence": None,
            "selected_features": [],
            "model_state_sha256": sha256_json({"constant": constant}),
        },
        "rolling_dirichlet_w20_a5": {
            **common,
            "model_id": "numbers3-n1-dirichlet-w20-a5",
            "model_family": "rolling_dirichlet",
            "configuration": {
                "window": 20,
                "alpha": 5.0,
                "decision_rule": "argmax P(|Y-candidate|<=1)",
            },
            "prediction": dirichlet,
            "confidence": dirichlet_conf,
            "selected_features": [],
            "model_state_sha256": sha256_json(
                {"history_tail": history[-20:].tolist(), "window": 20, "alpha": 5.0}
            ),
        },
        "tree_depth4": {
            **common,
            "model_id": "numbers3-n1-tree-depth4",
            "model_family": "decision_tree_classifier",
            "configuration": tree_config,
            "prediction": tree_pred,
            "confidence": tree_conf,
            "class_probability": tree_probability.tolist(),
            "selected_features": selected,
            "model_state_sha256": _pickle_sha256(tree),
        },
        "multinomial_logistic": {
            **common,
            "model_id": "numbers3-n1-multinomial-logistic",
            "model_family": "multinomial_logistic",
            "configuration": logistic_config,
            "prediction": logistic_pred,
            "confidence": logistic_conf,
            "class_probability": logistic_probability.tolist(),
            "selected_features": selected,
            "model_state_sha256": _pickle_sha256({"scaler": scaler, "model": logistic}),
        },
    }


@dataclass(frozen=True)
class LockResult:
    lock_file: str
    lock_sha256: str
    target_ds: str
    cutoff_ds: str
    predictions: dict[str, int]


def create_shadow_lock(
    project_root: Path,
    data_path: Path,
    output_dir: Path,
    target_ds: str,
    seed: int = 20260802,
) -> LockResult:
    project_root = project_root.resolve()
    data_path = data_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = load_dataset(data_path)
    target = pd.Timestamp(target_ds)
    cutoff = dataset["ds"].max()
    if target <= cutoff:
        raise ValueError(f"target_ds must be after cutoff_ds: target={target}, cutoff={cutoff}")

    data_hash = sha256_file(data_path)
    for existing in sorted(output_dir.glob("numbers3-n1-shadow-lock-*.json")):
        try:
            prior = json.loads(existing.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            prior.get("target_ds") == str(target)
            and prior.get("cutoff_ds") == str(cutoff)
            and prior.get("data", {}).get("sha256") == data_hash
            and prior.get("schema_version") == "1.1"
        ):
            raise FileExistsError(
                f"A schema 1.1 lock already exists for target/cutoff/data: {existing}"
            )

    models = train_shadow_predictions(dataset, target_ds=target, seed=seed)
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "created_at_utc": utc_now(),
        "status": "LOCKED_BEFORE_ACTUAL",
        "target_ds": str(target),
        "cutoff_ds": str(cutoff),
        "actual": None,
        "data": {
            "path": str(data_path),
            "sha256": data_hash,
            "rows": len(dataset),
        },
        "code": {
            "git_commit": git_value(project_root, "rev-parse", "HEAD"),
            "git_status_sha256": hashlib.sha256(
                (git_value(project_root, "status", "--short") or "").encode("utf-8")
            ).hexdigest(),
            "module_sha256": sha256_file(Path(__file__)),
        },
        "seed": seed,
        "primary_metric": "Hit@±1",
        "models": models,
    }
    lock_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    lock_file = output_dir / f"numbers3-n1-shadow-lock-{lock_id}.json"
    lock_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    lock_hash = sha256_file(lock_file)
    sha_file = lock_file.with_suffix(lock_file.suffix + ".sha256")
    sha_file.write_text(f"{lock_hash}  {lock_file.name}\n", encoding="utf-8")
    current = output_dir / "CURRENT.json"
    current_sha = output_dir / "CURRENT.json.sha256"
    for link, target_name in ((current, lock_file.name), (current_sha, sha_file.name)):
        try:
            link.unlink(missing_ok=True)
            link.symlink_to(target_name)
        except OSError:
            # Symlinks may be unavailable on some platforms; copy a pointer file instead.
            link.write_text(target_name + "\n", encoding="utf-8")
    return LockResult(
        lock_file=str(lock_file),
        lock_sha256=lock_hash,
        target_ds=str(target),
        cutoff_ds=str(cutoff),
        predictions={name: int(value["prediction"]) for name, value in models.items()},
    )
