from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EXPECTED_FREEZE_SHA256 = "deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c"
EXPECTED_SEMANTIC_SHA256 = "f406422fee3bc426c406443fa74f41a77361eed8987b00ce8143cd87b5d34abf"
KNOWN_REPLAY_SEMANTIC_SHA256 = "dd2bd61f213b14a560cd30612c95a11c42db95572ba059f9869a194481c36b59"
EXPECTED_RUNNER_SHA256 = "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
EXPECTED_EXPERIMENT_GIT_COMMIT = "179bcbc9a51a60f0badfe7faa25f3818ab686229"
EXPECTED_DEVELOPMENT_SHA256 = "f6e0292347cd03acea95b5c788eaa51436a8b9e7e42d2fc000e9b9d366e2557e"
EXPECTED_SELECTED_CANDIDATE = "catboost_seed_mean"
SEED = 1
OBJECT_REPR_RE = re.compile(
    r"^<(?P<class>[A-Za-z_][A-Za-z0-9_.]+) object at 0x[0-9A-Fa-f]+>$"
)
ADDRESS_RE = re.compile(r"0x[0-9A-Fa-f]+")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_text(repo: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    return p.returncode, p.stdout.strip()


def normalize_serialized(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): normalize_serialized(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [normalize_serialized(v) for v in value]
    if isinstance(value, np.generic):
        return normalize_serialized(value.item())
    if isinstance(value, str):
        match = OBJECT_REPR_RE.match(value)
        if match:
            return {"__python_object_class__": match.group("class")}
        return ADDRESS_RE.sub("0x<ADDR>", value) if "0x" in value else value
    return value


def typed_tree(value: Any, depth: int = 0) -> Any:
    typ = type(value)
    base = {"python_type": f"{typ.__module__}.{typ.__qualname__}"}
    if depth >= 10:
        return {**base, "truncated": True, "repr": repr(value)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return {**base, "value": value}
    if isinstance(value, np.generic):
        return {**base, "value": value.item(), "numpy_dtype": str(value.dtype)}
    if isinstance(value, dict):
        return {
            **base,
            "items": [
                {"key": typed_tree(k, depth + 1), "value": typed_tree(v, depth + 1)}
                for k, v in value.items()
            ],
        }
    if isinstance(value, (list, tuple)):
        return {**base, "items": [typed_tree(v, depth + 1) for v in value]}
    if callable(value):
        return {
            **base,
            "callable": True,
            "module": getattr(value, "__module__", None),
            "qualname": getattr(
                value,
                "__qualname__",
                getattr(value, "__name__", None),
            ),
            "repr": repr(value),
        }
    state: dict[str, Any] = {}
    try:
        for key, item in vars(value).items():
            if not key.startswith("_") and not key.endswith("_"):
                state[key] = typed_tree(item, depth + 1)
    except Exception:
        pass
    return {**base, "repr": repr(value), "public_state": state}


def exact_diff(left: Any, right: Any, path: str = "$") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right), key=str):
            sub = f"{path}.{key}"
            if key not in left:
                out.append({"path": sub, "kind": "MISSING_LEFT", "right": right[key]})
            elif key not in right:
                out.append({"path": sub, "kind": "MISSING_RIGHT", "left": left[key]})
            else:
                out.extend(exact_diff(left[key], right[key], sub))
        return out
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            out.append(
                {"path": path, "kind": "LENGTH", "left": len(left), "right": len(right)}
            )
        for idx, (lv, rv) in enumerate(zip(left, right)):
            out.extend(exact_diff(lv, rv, f"{path}[{idx}]"))
        return out
    if type(left) is not type(right) or left != right:
        out.append(
            {
                "path": path,
                "kind": "TYPE" if type(left) is not type(right) else "VALUE",
                "left": left,
                "right": right,
                "left_type": f"{type(left).__module__}.{type(left).__qualname__}",
                "right_type": f"{type(right).__module__}.{type(right).__qualname__}",
            }
        )
    return out


def recursive_diff(left: Any, right: Any, path: str = "$") -> list[dict[str, Any]]:
    if isinstance(left, dict) and isinstance(right, dict):
        out: list[dict[str, Any]] = []
        for key in sorted(set(left) | set(right), key=str):
            sub = f"{path}.{key}"
            if key not in left:
                out.append({"path": sub, "kind": "MISSING_LEFT", "right": right[key]})
            elif key not in right:
                out.append({"path": sub, "kind": "MISSING_RIGHT", "left": left[key]})
            else:
                out.extend(recursive_diff(left[key], right[key], sub))
        return out
    if isinstance(left, list) and isinstance(right, list):
        out = []
        if len(left) != len(right):
            out.append(
                {"path": path, "kind": "LENGTH", "left": len(left), "right": len(right)}
            )
        for idx, (lv, rv) in enumerate(zip(left, right)):
            out.extend(recursive_diff(lv, rv, f"{path}[{idx}]"))
        return out
    if (
        isinstance(left, (int, float))
        and isinstance(right, (int, float))
        and not isinstance(left, bool)
        and not isinstance(right, bool)
    ):
        same = bool(
            np.isclose(
                float(left),
                float(right),
                rtol=1e-12,
                atol=1e-12,
                equal_nan=True,
            )
        )
    else:
        same = left == right
    return [] if same else exact_diff(left, right, path)


def representation_only_diff(diff: dict[str, Any]) -> bool:
    if diff.get("kind") not in {"VALUE", "TYPE"}:
        return False
    left, right = diff.get("left"), diff.get("right")
    if isinstance(left, str) and isinstance(right, str):
        lm, rm = OBJECT_REPR_RE.match(left), OBJECT_REPR_RE.match(right)
        if lm and rm:
            return lm.group("class") == rm.group("class")
        return ADDRESS_RE.sub("0x<ADDR>", left) == ADDRESS_RE.sub("0x<ADDR>", right)
    if (
        isinstance(left, (int, float))
        and isinstance(right, (int, float))
        and not isinstance(left, bool)
        and not isinstance(right, bool)
    ):
        return bool(
            np.isclose(
                float(left),
                float(right),
                rtol=1e-12,
                atol=1e-12,
                equal_nan=True,
            )
        )
    return False


def compare_trials(expected_path: Path, replay: pd.DataFrame, out_csv: Path) -> dict[str, Any]:
    expected = pd.read_csv(expected_path)
    rows: list[dict[str, Any]] = []
    params = sorted(c for c in expected.columns if c.startswith("params_"))
    numbers_same = np.array_equal(
        expected["number"].to_numpy(int), replay["number"].to_numpy(int)
    )
    states_same = np.array_equal(
        expected["state"].astype(str).to_numpy(), replay["state"].astype(str).to_numpy()
    )
    ev = pd.to_numeric(expected["value"], errors="coerce").to_numpy(float)
    rv = pd.to_numeric(replay["value"], errors="coerce").to_numpy(float)
    objectives_same = len(ev) == len(rv) and bool(
        np.allclose(ev, rv, rtol=0.0, atol=1e-10, equal_nan=True)
    )
    params_same = len(expected) == len(replay)
    for col in params:
        if col not in replay.columns:
            params_same = False
            rows.append({"trial": None, "parameter": col, "kind": "MISSING_REPLAY_COLUMN"})
            continue
        for idx in range(min(len(expected), len(replay))):
            lv, rvv = expected.iloc[idx][col], replay.iloc[idx][col]
            if pd.isna(lv) or pd.isna(rvv):
                same = bool(pd.isna(lv) and pd.isna(rvv))
            else:
                try:
                    same = bool(
                        np.isclose(
                            float(lv),
                            float(rvv),
                            rtol=1e-12,
                            atol=1e-12,
                            equal_nan=True,
                        )
                    )
                except (TypeError, ValueError):
                    same = str(lv) == str(rvv)
            if not same:
                params_same = False
                rows.append(
                    {
                        "trial": int(expected.iloc[idx]["number"]),
                        "parameter": col,
                        "expected": None if pd.isna(lv) else lv,
                        "replay": None if pd.isna(rvv) else rvv,
                    }
                )
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["trial", "parameter", "expected", "replay", "kind"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    return {
        "trial_count_expected": len(expected),
        "trial_count_replay": len(replay),
        "numbers_same": bool(numbers_same),
        "states_same": bool(states_same),
        "objectives_same": objectives_same,
        "params_same": bool(params_same),
        "param_diff_rows": len(rows),
    }


def load_runner(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("phase7_runner_readonly", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_canonical_bridge(repo: Path) -> Any:
    path = repo / "tools" / "phase7_semantic_diagnosis" / "canonical_bridge.py"
    spec = importlib.util.spec_from_file_location("phase7_canonical_bridge", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical bridge: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def environment(repo: Path, runner: Path) -> dict[str, Any]:
    rc, head = git_text(repo, "rev-parse", "HEAD")
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "windows_version": platform.win32_ver(),
        "machine": platform.machine(),
        "packages": {
            name: package_version(name)
            for name in [
                "mlforecast",
                "optuna",
                "catboost",
                "lightgbm",
                "scikit-learn",
                "numpy",
                "pandas",
            ]
        },
        "git_head": head if rc == 0 else None,
        "runner_sha256": sha256_file(runner),
    }


def historical_environment(root: Path | None) -> dict[str, Any] | None:
    if root is None:
        return None
    path = root / "artifacts" / "ENVIRONMENT.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def environment_diff(old: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if old is None:
        return {
            "historical_available": False,
            "differences": [],
            "version_drift_detected": False,
        }
    diffs = []
    pairs = {
        "python": (old.get("python"), current.get("python")),
        "mlforecast": (old.get("mlforecast"), current["packages"].get("mlforecast")),
        "optuna": (old.get("optuna"), current["packages"].get("optuna")),
        "catboost": (old.get("catboost"), current["packages"].get("catboost")),
        "lightgbm": (old.get("lightgbm"), current["packages"].get("lightgbm")),
    }
    for key, (left, right) in pairs.items():
        if left is not None and right is not None:
            same = (
                str(left).split()[0] == str(right).split()[0]
                if key == "python"
                else str(left) == str(right)
            )
            if not same:
                diffs.append({"field": key, "frozen": left, "current": right})
    return {
        "historical_available": True,
        "differences": diffs,
        "version_drift_detected": bool(diffs),
    }


def progress(
    out: Path,
    phase: str,
    percent: int,
    completed: int,
    total: int,
    status: str = "RUNNING",
) -> None:
    write_json(
        out / "DIAGNOSIS_PROGRESS.json",
        {
            "phase": phase,
            "progress_percent": percent,
            "current_seed": SEED,
            "completed": completed,
            "total": total,
            "status": status,
            "updated_at_unix": time.time(),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="READ-ONLY Phase7 semantic config diagnosis; no Holdout actual access"
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--phase7-root", required=True)
    parser.add_argument("--phase6c-root", required=True)
    parser.add_argument("--phase6b-root")
    parser.add_argument("--development", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo = Path(args.repo)
    p7, p6c = Path(args.phase7_root), Path(args.phase6c_root)
    p6b = Path(args.phase6b_root) if args.phase6b_root else None
    development_path, out = Path(args.development), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if [p for p in out.iterdir() if p.name != "launcher.log"]:
        raise RuntimeError(f"diagnosis output directory is not empty: {out}")

    runner_path = p7 / "phase7_holdout.py"
    progress_path = p7 / "artifacts" / "progress.json"
    freeze_path = p6c / "artifacts" / "CANDIDATE_FREEZE.json"
    for path in [runner_path, progress_path, freeze_path, development_path]:
        if not path.is_file():
            raise FileNotFoundError(path)

    runner_sha = sha256_file(runner_path)
    if runner_sha != EXPECTED_RUNNER_SHA256:
        raise RuntimeError(f"Phase7 runner SHA mismatch: {runner_sha}")

    rc, repo_head = git_text(repo, "rev-parse", "HEAD")
    if rc != 0:
        raise RuntimeError("cannot resolve repository HEAD")
    present, _ = git_text(
        repo,
        "cat-file",
        "-e",
        f"{EXPECTED_EXPERIMENT_GIT_COMMIT}^{{commit}}",
    )
    if present != 0:
        raise RuntimeError("frozen experiment commit is not present in this checkout")
    ancestor, _ = git_text(
        repo,
        "merge-base",
        "--is-ancestor",
        EXPECTED_EXPERIMENT_GIT_COMMIT,
        "HEAD",
    )
    if ancestor != 0:
        raise RuntimeError("current checkout is not a descendant of the frozen experiment commit")

    p7_progress = json.loads(progress_path.read_text(encoding="utf-8"))
    holdout_draws = int(p7_progress.get("holdout_draws_done", -1))
    actuals_accessed = int(p7_progress.get("actuals_accessed", -1))
    if holdout_draws != 0 or actuals_accessed != 0:
        raise RuntimeError(
            f"Holdout integrity gate failed: draws={holdout_draws}, actuals={actuals_accessed}"
        )
    lock_dir = p7 / "artifacts" / "prediction_locks"
    lock_files = (
        sorted(p.name for p in lock_dir.glob("*") if p.is_file())
        if lock_dir.exists()
        else []
    )
    if lock_files:
        raise RuntimeError(f"prediction locks already exist: {lock_files}")

    development_sha = sha256_file(development_path)
    if development_sha != EXPECTED_DEVELOPMENT_SHA256:
        raise RuntimeError(f"development SHA mismatch: {development_sha}")
    freeze_sha = sha256_file(freeze_path)
    if freeze_sha != EXPECTED_FREEZE_SHA256:
        raise RuntimeError(f"Candidate Freeze SHA mismatch: {freeze_sha}")

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("selected_candidate") != EXPECTED_SELECTED_CANDIDATE:
        raise RuntimeError("frozen selected candidate mismatch")
    if freeze.get("git_commit") != EXPECTED_EXPERIMENT_GIT_COMMIT:
        raise RuntimeError("frozen experiment git commit mismatch")
    if freeze.get("development_sha256") != EXPECTED_DEVELOPMENT_SHA256:
        raise RuntimeError("frozen development SHA mismatch")
    if bool(freeze.get("holdout_opened")) or bool(freeze.get("holdout_used_for_selection")):
        raise RuntimeError("freeze metadata indicates Holdout access/use")

    component = next(
        (
            c
            for c in freeze.get("components", [])
            if c.get("model") == "AutoCatboost" and int(c.get("seed")) == SEED
        ),
        None,
    )
    if component is None:
        raise RuntimeError("seed=1 AutoCatboost component missing")
    if (
        str(component.get("objective")) != "raw_hit_at_1"
        or int(component.get("num_samples", -1)) != 20
        or not np.isclose(
            float(component.get("weight", float("nan"))),
            0.25,
            atol=1e-12,
            rtol=0.0,
        )
    ):
        raise RuntimeError("frozen seed=1 contract mismatch")

    frozen_dir = p6c / "artifacts" / "frozen_component_evidence"
    frozen_config_path = frozen_dir / str(component["frozen_config_file"])
    frozen_trials_path = frozen_dir / str(component["frozen_trials_file"])
    if (
        sha256_file(frozen_config_path) != str(component["frozen_config_sha256"])
        or sha256_file(frozen_trials_path) != str(component["frozen_trials_sha256"])
    ):
        raise RuntimeError("frozen component evidence SHA mismatch")

    frozen_doc = json.loads(frozen_config_path.read_text(encoding="utf-8"))
    frozen_config = frozen_doc["config"]
    frozen_semantic = str(
        frozen_doc.get("config_sha256") or component.get("semantic_config_sha256")
    )
    if frozen_semantic != EXPECTED_SEMANTIC_SHA256:
        raise RuntimeError(f"unexpected frozen semantic SHA: {frozen_semantic}")

    current_env = environment(repo, runner_path)
    old_env = historical_environment(p6b)
    env_cmp = environment_diff(old_env, current_env)
    write_json(out / "ENVIRONMENT_CURRENT.json", current_env)
    write_json(out / "ENVIRONMENT_DIFF.json", {"historical_environment": old_env, **env_cmp})
    progress(out, "FROZEN_EVIDENCE", 20, 0, 20)

    runner = load_runner(runner_path)
    development = pd.read_csv(development_path)
    hpo_wide = development.iloc[: -int(runner.OUTER_WINDOWS)].copy()
    hpo_panel = runner.panel(hpo_wide)

    def fit_config(trial: Any) -> dict[str, Any]:
        del trial
        return {"static_features": []}

    auto = runner.AutoMLForecast(
        models={"AutoCatboost": runner.AutoCatboost()},
        freq=1,
        season_length=1,
        fit_config=fit_config,
        num_threads=1,
        reuse_cv_splits=True,
    )
    sampler = runner.optuna.samplers.TPESampler(seed=SEED)
    progress(out, "REPLAY_HPO", 35, 0, int(runner.NUM_SAMPLES))
    auto.fit(
        df=hpo_panel,
        n_windows=int(runner.INNER_WINDOWS),
        h=1,
        num_samples=int(runner.NUM_SAMPLES),
        step_size=1,
        input_size=None,
        refit=False,
        loss=runner.raw_hit_loss,
        id_col="unique_id",
        time_col="ds",
        target_col="y",
        study_kwargs={"sampler": sampler},
        optimize_kwargs={"n_jobs": 1},
    )

    study = auto.results_["AutoCatboost"]
    replay_trials = study.trials_dataframe()
    replay_trials.to_csv(out / "REPLAY_TRIALS_SEED1.csv", index=False)
    trial_cmp = compare_trials(
        frozen_trials_path,
        replay_trials,
        out / "TRIAL_PARAM_DIFF.csv",
    )

    replay_raw = copy.deepcopy(study.best_trial.user_attrs["config"])
    replay_serialized = json.loads(json.dumps(replay_raw, default=str))
    replay_semantic = sha256_json(replay_serialized)
    frozen_canonical = normalize_serialized(frozen_config)
    replay_canonical = normalize_serialized(replay_serialized)
    raw_diffs = exact_diff(frozen_config, replay_serialized)
    tolerant_diffs = recursive_diff(frozen_config, replay_serialized)
    canonical_diffs = exact_diff(frozen_canonical, replay_canonical)
    repr_only = bool(raw_diffs) and all(representation_only_diff(d) for d in raw_diffs)

    write_json(out / "RAW_FROZEN_CONFIG.json", frozen_doc)
    write_json(
        out / "RAW_REPLAY_CONFIG.json",
        {
            "best_trial": int(study.best_trial.number),
            "best_inner_loss": float(study.best_value),
            "config": replay_serialized,
            "config_sha256": replay_semantic,
        },
    )
    write_json(out / "FROZEN_CONFIG_TYPED_TREE.json", typed_tree(frozen_config))
    write_json(out / "REPLAY_CONFIG_TYPED_TREE.json", typed_tree(replay_raw))
    write_json(out / "FROZEN_CONFIG_CANONICAL.json", frozen_canonical)
    write_json(out / "REPLAY_CONFIG_CANONICAL.json", replay_canonical)
    write_json(
        out / "SEMANTIC_CONFIG_DIFF.json",
        {
            "raw_diff_count": len(raw_diffs),
            "raw_differences": raw_diffs,
            "tolerant_raw_diff_count": len(tolerant_diffs),
            "tolerant_raw_differences": tolerant_diffs,
            "canonical_diff_count": len(canonical_diffs),
            "canonical_differences": canonical_diffs,
            "all_raw_differences_representation_only": repr_only,
        },
    )

    best_trial_same = int(frozen_doc["best_trial"]) == int(study.best_trial.number)
    best_objective_same = bool(
        np.isclose(
            float(frozen_doc["best_inner_loss"]),
            float(study.best_value),
            rtol=0.0,
            atol=1e-10,
            equal_nan=True,
        )
    )
    trial_params_same = bool(
        trial_cmp["numbers_same"]
        and trial_cmp["states_same"]
        and trial_cmp["objectives_same"]
        and trial_cmp["params_same"]
    )
    semantic_values_same = not canonical_diffs
    version_drift = bool(env_cmp["version_drift_detected"])
    true_drift = bool(
        (not best_trial_same)
        or (not trial_params_same)
        or (not semantic_values_same and not version_drift)
    )
    type_only = bool(repr_only and semantic_values_same)

    bridge = load_canonical_bridge(repo)
    bridge_result = bridge.verify_phase7_canonical_bridge(
        repo=repo,
        frozen_config=frozen_config,
        replay_config=replay_raw,
        legacy_frozen_sha256=frozen_semantic,
        legacy_replay_sha256=replay_semantic,
        selected_candidate=str(freeze.get("selected_candidate")),
        frozen_best_trial=int(frozen_doc["best_trial"]),
        replay_best_trial=int(study.best_trial.number),
        frozen_best_objective=float(frozen_doc["best_inner_loss"]),
        replay_best_objective=float(study.best_value),
        trial_comparison=trial_cmp,
        replay_best_params=study.best_trial.params,
        mlforecast_version=current_env["packages"].get("mlforecast"),
        runner_sha256=runner_sha,
        experiment_git_commit=str(freeze.get("git_commit")),
    )
    write_json(
        out / "FROZEN_CONFIG_CANONICAL_V1.json",
        bridge_result["frozen_canonical_document"],
    )
    write_json(
        out / "REPLAY_CONFIG_CANONICAL_V1.json",
        bridge_result["replay_canonical_document"],
    )
    bridge_public = {
        key: value
        for key, value in bridge_result.items()
        if key not in {"frozen_canonical_document", "replay_canonical_document"}
    }
    write_json(out / "CANONICAL_SEMANTIC_BRIDGE_V1.json", bridge_public)

    if (
        repr_only
        and semantic_values_same
        and best_trial_same
        and best_objective_same
        and trial_params_same
        and not version_drift
        and bridge_result["canonical_semantic_match"] is True
    ):
        classification, status, safe_change = "SERIALIZATION_ONLY", "PASS", True
        reason = (
            "Raw serialized configs differ only by unstable representation while canonical "
            "semantic values, best trial/objective, trial sequence, environment, and versioned "
            "canonical semantic SHA all match."
        )
        next_action = (
            "Independently review the canonical verifier bridge evidence; keep Holdout sealed "
            "until that review is complete."
        )
    elif version_drift and trial_params_same:
        classification, status, safe_change = "VERSION_DRIFT", "BLOCKED", False
        reason = "Runtime/package drift prevents certification of semantic equivalence."
        next_action = (
            "Reconstruct the original Phase6B runtime and repeat this development-only replay."
        )
    elif true_drift:
        classification, status, safe_change = "TRUE_CONFIG_DRIFT", "BLOCKED", False
        reason = (
            "Best trial/trial sequence or canonical semantic values differ beyond "
            "representation-only normalization."
        )
        next_action = (
            "Keep Holdout sealed and investigate the development-only reproducibility contract."
        )
    else:
        classification, status, safe_change = "UNKNOWN", "BLOCKED", False
        reason = (
            "Available evidence does not prove serialization-only equivalence, version drift, "
            "or true semantic drift."
        )
        next_action = "Review generated typed/raw/canonical evidence without accessing Holdout."

    write_json(
        out / "TRIAL_BEST_COMPARISON.json",
        {
            "frozen": {
                "best_trial": int(frozen_doc["best_trial"]),
                "best_inner_loss": float(frozen_doc["best_inner_loss"]),
                "semantic_config_sha256": frozen_semantic,
            },
            "replay": {
                "best_trial": int(study.best_trial.number),
                "best_inner_loss": float(study.best_value),
                "semantic_config_sha256": replay_semantic,
            },
            "best_trial_same": best_trial_same,
            "best_objective_same": best_objective_same,
            "trial_replay": trial_cmp,
            "canonical_semantic_schema": bridge_result["canonical_semantic_schema"],
            "canonical_semantic_sha256_frozen": bridge_result[
                "canonical_semantic_sha256_frozen"
            ],
            "canonical_semantic_sha256_replay": bridge_result[
                "canonical_semantic_sha256_replay"
            ],
            "canonical_semantic_match": bridge_result["canonical_semantic_match"],
        },
    )

    diagnosis = {
        "status": status,
        "classification": classification,
        "holdout_draws_accessed": holdout_draws,
        "actuals_accessed": actuals_accessed,
        "candidate_freeze_sha256": freeze_sha,
        "expected_semantic_sha256": frozen_semantic,
        "replay_semantic_sha256": replay_semantic,
        "legacy_semantic_sha256_frozen": bridge_result["legacy_semantic_sha256_frozen"],
        "legacy_semantic_sha256_replay": bridge_result["legacy_semantic_sha256_replay"],
        "legacy_semantic_hash_match": bridge_result["legacy_hash_match"],
        "canonical_semantic_schema": bridge_result["canonical_semantic_schema"],
        "canonical_semantic_sha256_frozen": bridge_result[
            "canonical_semantic_sha256_frozen"
        ],
        "canonical_semantic_sha256_replay": bridge_result[
            "canonical_semantic_sha256_replay"
        ],
        "canonical_semantic_match": bridge_result["canonical_semantic_match"],
        "canonical_bridge_state_source": bridge_result["bridge_state_source"],
        "canonical_bridge_differences_state": bridge_result["differences_state"],
        "known_prior_replay_semantic_sha256": KNOWN_REPLAY_SEMANTIC_SHA256,
        "replay_hash_matches_known_prior": replay_semantic == KNOWN_REPLAY_SEMANTIC_SHA256,
        "expected_runner_sha256": EXPECTED_RUNNER_SHA256,
        "actual_runner_sha256": runner_sha,
        "expected_experiment_git_commit": EXPECTED_EXPERIMENT_GIT_COMMIT,
        "tool_repo_head": repo_head,
        "experiment_commit_present": True,
        "experiment_commit_is_ancestor": True,
        "best_trial_same": best_trial_same,
        "best_objective_same": best_objective_same,
        "trial_params_same": trial_params_same,
        "semantic_values_same": semantic_values_same,
        "type_only_differences": type_only,
        "version_drift_detected": version_drift,
        "true_config_drift_detected": true_drift,
        "safe_to_change_verifier": safe_change,
        "safe_to_continue_holdout": False,
        "reason": reason,
        "next_action": next_action,
        "development_sha256": development_sha,
        "phase7_progress_phase_before_diagnosis": str(p7_progress.get("phase")),
        "phase7_prediction_lock_files_before_diagnosis": lock_files,
        "diagnosis_note": (
            "No canonical/Holdout dataset path is accepted by this program; Phase7 and "
            "Candidate Freeze are read-only."
        ),
    }
    write_json(out / "DIAGNOSIS.json", diagnosis)

    md = [
        "# Phase 7 Semantic Config Diagnosis",
        "",
        f"- Status: **{status}**",
        f"- Classification: **{classification}**",
        f"- Holdout draws accessed: **{holdout_draws}**",
        f"- Actuals accessed: **{actuals_accessed}**",
        f"- Legacy frozen SHA: `{frozen_semantic}`",
        f"- Legacy replay SHA: `{replay_semantic}`",
        f"- Canonical schema: `{bridge_result['canonical_semantic_schema']}`",
        f"- Canonical frozen SHA: `{bridge_result['canonical_semantic_sha256_frozen']}`",
        f"- Canonical replay SHA: `{bridge_result['canonical_semantic_sha256_replay']}`",
        f"- Canonical SHA match: **{bridge_result['canonical_semantic_match']}**",
        "",
        "## Reason",
        "",
        reason,
        "",
        "## Raw differences",
        "",
    ]
    md.extend(
        [
            f"- `{d['path']}` {d['kind']}: `{d.get('left')}` -> `{d.get('right')}`"
            for d in raw_diffs
        ]
        or ["- None"]
    )
    md += ["", "## Canonical differences", ""]
    md.extend(
        [
            f"- `{d['path']}` {d['kind']}: `{d.get('left')}` -> `{d.get('right')}`"
            for d in canonical_diffs
        ]
        or ["- None"]
    )
    md += ["", "## Next action", "", next_action, ""]
    (out / "SEMANTIC_CONFIG_DIFF.md").write_text("\n".join(md), encoding="utf-8")
    (out / "README.md").write_text(
        "# Phase7 semantic diagnosis artifacts\n\n"
        "READ-ONLY development-only forensic replay. Holdout and Candidate Freeze remain untouched.\n",
        encoding="utf-8",
    )
    progress(
        out,
        "COMPLETE",
        100,
        int(runner.NUM_SAMPLES),
        int(runner.NUM_SAMPLES),
        status,
    )

    manifest = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name not in {
            "ARTIFACT_MANIFEST.json",
            "SHA256SUMS",
            "launcher.log",
        }:
            manifest.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    write_json(
        out / "ARTIFACT_MANIFEST.json",
        {"holdout_accessed": False, "files": manifest},
    )
    lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(out.iterdir())
        if path.is_file() and path.name not in {"SHA256SUMS", "launcher.log"}
    ]
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"STATUS={status}")
    print(f"CLASSIFICATION={classification}")
    print(f"HOLDOUT_DRAWS_ACCESSED={holdout_draws}")
    print(f"ACTUALS_ACCESSED={actuals_accessed}")
    print(f"EXPECTED_SEMANTIC_SHA256={frozen_semantic}")
    print(f"REPLAY_SEMANTIC_SHA256={replay_semantic}")
    print(f"CANONICAL_SEMANTIC_SCHEMA={bridge_result['canonical_semantic_schema']}")
    print(
        "CANONICAL_FROZEN_SEMANTIC_SHA256="
        f"{bridge_result['canonical_semantic_sha256_frozen']}"
    )
    print(
        "CANONICAL_REPLAY_SEMANTIC_SHA256="
        f"{bridge_result['canonical_semantic_sha256_replay']}"
    )
    print(
        "CANONICAL_SEMANTIC_MATCH="
        f"{'YES' if bridge_result['canonical_semantic_match'] else 'NO'}"
    )
    print(f"SAFE_TO_CHANGE_VERIFIER={'YES' if safe_change else 'NO'}")
    print("SAFE_TO_CONTINUE_HOLDOUT=NO")
    print(f"OUTPUT={out}")
    return 0 if classification == "SERIALIZATION_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
