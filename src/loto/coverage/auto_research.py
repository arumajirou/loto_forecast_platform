from __future__ import annotations

import hashlib
import itertools
import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from loto.data.lineage import atomic_write_json
from loto.models.catalog import get_model_spec, list_model_specs

GAME_GEOMETRY: dict[str, tuple[int, int]] = {
    "mini": (5, 31),
    "miniloto": (5, 31),
    "loto6": (6, 43),
    "loto7": (7, 37),
}


@dataclass(frozen=True)
class SearchBudget:
    max_experiments: int = 500
    max_runtime_seconds: int = 86400
    max_consecutive_failures: int = 20
    max_candidates: int = 5000
    target_coverage: float = 0.90
    calibration_margin: float = 0.02
    tolerance: int = 1
    stop_when_target_met: bool = True


@dataclass(frozen=True)
class ExperimentProposal:
    experiment_id: str
    game: str
    model_id: str
    params: dict[str, Any]
    ensemble: list[str]
    pool_size: int
    per_position_top: int
    beam_width: int
    diversity_penalty: float
    seed: int
    source: str = "grid"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()[:16]


def _load_yaml(path: str | Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("auto research config must be a mapping")
    return raw


def _number_columns(frame: pd.DataFrame, game: str) -> list[str]:
    count, _ = GAME_GEOMETRY[game]
    cols = [f"n{i}" for i in range(1, count + 1)]
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise ValueError(f"{game}: missing number columns: {missing}")
    return cols


def _read_game_data(path: str | Path, game: str) -> np.ndarray:
    frame = pd.read_csv(path)
    cols = _number_columns(frame, game)
    values = frame[cols].apply(pd.to_numeric, errors="raise").to_numpy(dtype=int)
    _, maximum = GAME_GEOMETRY[game]
    if np.any(values < 1) or np.any(values > maximum):
        raise ValueError(f"{game}: values outside 1..{maximum}")
    if np.any(np.diff(values, axis=1) <= 0):
        raise ValueError(f"{game}: rows must be strictly increasing")
    return values


def _legalize(row: Iterable[float], count: int, maximum: int) -> tuple[int, ...]:
    values = np.clip(np.rint(np.asarray(list(row), dtype=float)), 1, maximum).astype(int)
    values.sort()
    for i in range(1, count):
        values[i] = max(values[i], values[i - 1] + 1)
    if values[-1] > maximum:
        values -= values[-1] - maximum
        for i in range(count - 2, -1, -1):
            values[i] = min(values[i], values[i + 1] - 1)
    if values[0] < 1:
        values = np.arange(1, count + 1)
    return tuple(int(x) for x in values)


def _point(
    history: np.ndarray, method: str, params: dict[str, Any], maximum: int
) -> tuple[int, ...]:
    count = history.shape[1]
    window = int(params.get("window", min(100, len(history))))
    sample = history[-min(window, len(history)) :]
    if method in {"uniform", "median", "position-median"}:
        center = np.median(sample, axis=0)
    elif method in {"historic-average", "stats-historic-average", "stats-autoets"}:
        center = np.mean(sample, axis=0)
    elif method in {"frequency", "recent-median"}:
        center = np.median(sample, axis=0)
    elif method in {"stats-naive"}:
        center = sample[-1]
    elif method in {"stats-autoarima", "ridge-position", "mlforecast-ridge"}:
        lags = [int(x) for x in params.get("lags", [1, 2, 3, 5, 10, 20]) if int(x) < len(sample)]
        if not lags:
            center = np.mean(sample, axis=0)
        else:
            x_rows, y_rows = [], []
            max_lag = max(lags)
            for t in range(max_lag, len(sample)):
                x_rows.append(np.concatenate([sample[t - lag] for lag in lags]))
                y_rows.append(sample[t])
            if len(x_rows) < 5:
                center = np.mean(sample, axis=0)
            else:
                x = np.asarray(x_rows, float)
                y = np.asarray(y_rows, float)
                alpha = float(params.get("alpha", 1.0))
                beta = np.linalg.solve(x.T @ x + alpha * np.eye(x.shape[1]), x.T @ y)
                center = np.concatenate([sample[-lag] for lag in lags]) @ beta
    else:
        # Unsupported heavy/optional models get a deterministic surrogate
        # only when explicitly allowed.
        if not params.get("allow_surrogate", False):
            raise RuntimeError(
                f"model {method} requires its provider worker; "
                "set allow_surrogate only for orchestration smoke tests"
            )
        center = np.median(sample, axis=0)
    return _legalize(center, count, maximum)


def _walk_forward(
    data: np.ndarray, start: int, end: int, proposal: ExperimentProposal, maximum: int
) -> tuple[np.ndarray, np.ndarray]:
    actual, predicted = [], []
    methods = proposal.ensemble or [proposal.model_id]
    for index in range(start, end):
        history = data[:index]
        points = [_point(history, m, proposal.params, maximum) for m in methods]
        prediction = _legalize(np.median(np.asarray(points), axis=0), data.shape[1], maximum)
        actual.append(data[index])
        predicted.append(prediction)
    return np.asarray(actual, int), np.asarray(predicted, int)


def _candidate_pool(
    center: np.ndarray,
    residuals: np.ndarray,
    count: int,
    maximum: int,
    proposal: ExperimentProposal,
) -> list[tuple[int, ...]]:
    rng = np.random.default_rng(proposal.seed)
    seen: set[tuple[int, ...]] = set()
    pool: list[tuple[int, ...]] = []

    def add(row: Iterable[float]) -> None:
        legal = _legalize(row, count, maximum)
        if legal not in seen:
            seen.add(legal)
            pool.append(legal)

    add(center)
    # Empirical residual vectors preserve cross-position dependence.
    for residual in residuals:
        add(center + residual)
        add(center - residual)
        if len(pool) >= proposal.pool_size:
            return pool
    scales = np.maximum(np.std(residuals, axis=0) if len(residuals) else np.ones(count), 1.0)
    while len(pool) < proposal.pool_size:
        draw = center + rng.normal(0.0, scales)
        add(draw)
        if len(seen) >= math.comb(maximum, count):
            break
    return pool


def _evaluate_general(
    actual: np.ndarray, candidates: list[tuple[int, ...]], tolerance: int
) -> dict[str, Any]:
    cand = np.asarray(candidates, int)
    errors = np.abs(actual[:, None, :] - cand[None, :, :])
    row_ok = np.max(errors, axis=2) <= tolerance
    best = np.argmin(np.mean(errors, axis=2), axis=1)
    best_errors = errors[np.arange(len(actual)), best]
    return {
        "draws": int(len(actual)),
        "candidate_count": int(len(candidates)),
        "row_within_tolerance": float(np.mean(np.any(row_ok, axis=1))),
        "element_within_tolerance": float(np.mean(best_errors <= tolerance)),
        "mean_best_mae": float(np.mean(best_errors)),
        "exact_row_rate": float(np.mean(np.any(np.max(errors, axis=2) == 0, axis=1))),
    }


def _greedy_general(
    actual: np.ndarray,
    pool: list[tuple[int, ...]],
    *,
    target: float,
    tolerance: int,
    max_candidates: int,
    diversity: float,
) -> tuple[list[tuple[int, ...]], list[dict[str, Any]]]:
    masks = np.vstack(
        [np.max(np.abs(actual - np.asarray(row)[None, :]), axis=1) <= tolerance for row in pool]
    )
    uncovered = np.ones(len(actual), bool)
    remaining = np.ones(len(pool), bool)
    selected: list[tuple[int, ...]] = []
    trace: list[dict[str, Any]] = []
    target_count = math.ceil(target * len(actual))
    while int((~uncovered).sum()) < target_count and len(selected) < max_candidates:
        gains = np.sum(masks[:, uncovered], axis=1).astype(float)
        gains[~remaining] = -np.inf
        if selected and diversity > 0:
            pa = np.asarray(pool, float)
            sa = np.asarray(selected, float)
            gains += diversity * np.min(
                np.mean(np.abs(pa[:, None, :] - sa[None, :, :]), axis=2), axis=1
            )
        idx = int(np.argmax(gains))
        raw = int(np.sum(masks[idx] & uncovered))
        if raw <= 0:
            if not selected:
                idx = 0
                selected.append(pool[idx])
                trace.append(
                    {"step": 1, "candidate": list(pool[idx]), "newly_covered": 0, "coverage": 0.0}
                )
            break
        remaining[idx] = False
        selected.append(pool[idx])
        uncovered &= ~masks[idx]
        trace.append(
            {
                "step": len(selected),
                "candidate": list(pool[idx]),
                "newly_covered": raw,
                "coverage": float(np.mean(~uncovered)),
            }
        )
    return selected, trace


def _expand_space(space: dict[str, Any]) -> Iterable[dict[str, Any]]:
    if not space:
        yield {}
        return
    keys = list(space)
    values = [v if isinstance(v, list) else [v] for v in (space[k] for k in keys)]
    for combo in itertools.product(*values):
        yield dict(zip(keys, combo, strict=True))


def build_grid(raw: dict[str, Any], game: str) -> list[ExperimentProposal]:
    search = raw.get("search", {})
    models = search.get("models", "available")
    if models == "available":
        model_ids = [s.model_id for s in list_model_specs(available_only=True)]
    elif models == "all":
        model_ids = [s.model_id for s in list_model_specs()]
    else:
        model_ids = list(models)
    params_by_model = search.get("parameter_spaces", {})
    ensembles = search.get("ensembles", [[]])
    common = search.get("common", {})
    proposals: list[ExperimentProposal] = []
    for model_id in model_ids:
        try:
            get_model_spec(model_id)
        except KeyError:
            continue
        for params in _expand_space(params_by_model.get(model_id, {})):
            for ensemble in ensembles:
                payload = {
                    "game": game,
                    "model": model_id,
                    "params": params,
                    "ensemble": ensemble,
                    "common": common,
                }
                proposals.append(
                    ExperimentProposal(
                        experiment_id=_hash(payload),
                        game=game,
                        model_id=model_id,
                        params=params,
                        ensemble=list(ensemble),
                        pool_size=int(common.get("pool_size", 20000)),
                        per_position_top=int(common.get("per_position_top", 7)),
                        beam_width=int(common.get("beam_width", 20000)),
                        diversity_penalty=float(common.get("diversity_penalty", 0.05)),
                        seed=int(common.get("seed", 42)),
                    )
                )
    return proposals


class LocalLLMClient:
    def __init__(self, config: dict[str, Any]):
        self.base_url = str(config.get("base_url", "http://127.0.0.1:17200/v1")).rstrip("/")
        self.model = str(config.get("model", "ornith9b_mtp_fast"))
        self.timeout = int(config.get("timeout_seconds", 300))
        self.temperature = float(config.get("temperature", 0.1))
        self.max_tokens = int(config.get("max_tokens", 1500))

    def propose(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        prompt = (
            "You optimize a leakage-safe lottery coverage experiment. "
            "Return JSON only with key proposals. Each proposal has "
            "model_id, params, ensemble, pool_size, diversity_penalty. "
            "Never claim success; suggest bounded experiments that may "
            "improve validation row_within_tolerance while reducing "
            "candidate_count.\n" + json.dumps(context, ensure_ascii=False, default=str)
        )
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
        ).encode()
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload["choices"][0]["message"]["content"]
            start, end = text.find("{"), text.rfind("}")
            parsed = json.loads(text[start : end + 1])
            return list(parsed.get("proposals", []))
        except (OSError, ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError):
            return []


def _proposal_from_llm(
    item: dict[str, Any], game: str, defaults: dict[str, Any]
) -> ExperimentProposal | None:
    model_id = str(item.get("model_id", ""))
    try:
        get_model_spec(model_id)
    except KeyError:
        return None
    payload = {"game": game, "llm": item}
    return ExperimentProposal(
        experiment_id=_hash(payload),
        game=game,
        model_id=model_id,
        params=dict(item.get("params", {})),
        ensemble=list(item.get("ensemble", [])),
        pool_size=min(
            int(item.get("pool_size", defaults.get("pool_size", 20000))),
            int(defaults.get("pool_size_max", 100000)),
        ),
        per_position_top=int(defaults.get("per_position_top", 7)),
        beam_width=int(defaults.get("beam_width", 20000)),
        diversity_penalty=float(
            item.get("diversity_penalty", defaults.get("diversity_penalty", 0.05))
        ),
        seed=int(defaults.get("seed", 42)),
        source="local_llm",
    )


def run_auto_research(config_path: str | Path) -> dict[str, Any]:
    raw = _load_yaml(config_path)
    output = Path(raw.get("output", "runs/auto-coverage"))
    output.mkdir(parents=True, exist_ok=True)
    budget = SearchBudget(**raw.get("budget", {}))
    games_cfg = raw.get("games", {})
    state_path = output / "state.json"
    state = (
        json.loads(state_path.read_text())
        if state_path.exists() and raw.get("resume", True)
        else {"completed": {}, "started_at": time.time()}
    )
    started = time.time()
    all_summaries: dict[str, Any] = {}
    llm_cfg = raw.get("local_llm", {})
    llm = LocalLLMClient(llm_cfg) if llm_cfg.get("enabled", False) else None
    for game, game_cfg in games_cfg.items():
        if game not in GAME_GEOMETRY:
            all_summaries[game] = {"status": "UNSUPPORTED_GAME"}
            continue
        data = _read_game_data(game_cfg["input"], game)
        count, maximum = GAME_GEOMETRY[game]
        split = game_cfg.get("split", {})
        test = int(split.get("test_size", 50))
        val = int(split.get("validation_size", 80))
        cal = int(split.get("calibration_size", 80))
        min_train = int(split.get("min_train_size", 250))
        test_start = len(data) - test
        val_start = test_start - val
        cal_start = val_start - cal
        if cal_start < min_train:
            raise ValueError(f"{game}: insufficient data for split")
        queue = build_grid(raw, game)
        seen = set(state["completed"])
        consecutive_failures = 0
        game_results = []
        target_met = False
        while (
            queue
            and len(game_results) < budget.max_experiments
            and time.time() - started < budget.max_runtime_seconds
        ):
            proposal = queue.pop(0)
            if proposal.experiment_id in seen:
                continue
            rec: dict[str, Any] = {"proposal": proposal.to_dict(), "started_at": time.time()}
            try:
                cal_actual, cal_pred = _walk_forward(data, cal_start, val_start, proposal, maximum)
                val_actual, val_pred = _walk_forward(data, val_start, test_start, proposal, maximum)
                residuals = cal_actual - cal_pred
                center = np.rint(np.median(val_pred, axis=0)).astype(int)
                pool = _candidate_pool(center, residuals, count, maximum, proposal)
                selected, trace = _greedy_general(
                    cal_actual,
                    pool,
                    target=min(1.0, budget.target_coverage + budget.calibration_margin),
                    tolerance=budget.tolerance,
                    max_candidates=min(budget.max_candidates, proposal.pool_size),
                    diversity=proposal.diversity_penalty,
                )
                if not selected:
                    raise RuntimeError("no candidates selected")
                cal_eval = _evaluate_general(cal_actual, selected, budget.tolerance)
                val_eval = _evaluate_general(val_actual, selected, budget.tolerance)
                rec.update(
                    {
                        "status": "SUCCEEDED",
                        "calibration": cal_eval,
                        "validation": val_eval,
                        "candidate_count": len(selected),
                        "trace": trace,
                        "elapsed_seconds": time.time() - rec["started_at"],
                    }
                )
                candidate_path = output / f"{game}-{proposal.experiment_id}-candidates.csv"
                pd.DataFrame(selected, columns=[f"n{i}" for i in range(1, count + 1)]).to_csv(
                    candidate_path, index=False
                )
                rec["candidate_artifact"] = str(candidate_path)
                consecutive_failures = 0
                target_met = val_eval["row_within_tolerance"] >= budget.target_coverage
            except Exception as exc:
                rec.update(
                    {
                        "status": "FAILED",
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_seconds": time.time() - rec["started_at"],
                    }
                )
                consecutive_failures += 1
            game_results.append(rec)
            state["completed"][proposal.experiment_id] = rec
            atomic_write_json(state_path, state)
            with (output / "experiments.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            if target_met and budget.stop_when_target_met:
                break
            if consecutive_failures >= budget.max_consecutive_failures:
                break
            if llm and len(game_results) % int(llm_cfg.get("every_n_experiments", 10)) == 0:
                successful = [r for r in game_results if r["status"] == "SUCCEEDED"]
                best = sorted(
                    successful,
                    key=lambda r: (
                        -r["validation"]["row_within_tolerance"],
                        r["candidate_count"],
                        r["validation"]["mean_best_mae"],
                    ),
                )[:10]
                context = {
                    "game": game,
                    "target": budget.target_coverage,
                    "budget_remaining": budget.max_experiments - len(game_results),
                    "best": best,
                    "failed_recent": [r for r in game_results[-10:] if r["status"] == "FAILED"],
                }
                for item in llm.propose(context):
                    p = _proposal_from_llm(item, game, raw.get("search", {}).get("common", {}))
                    if p and p.experiment_id not in seen:
                        queue.append(p)
        successful = [r for r in game_results if r["status"] == "SUCCEEDED"]
        best = (
            sorted(
                successful,
                key=lambda r: (
                    -r["validation"]["row_within_tolerance"],
                    r["candidate_count"],
                    r["validation"]["mean_best_mae"],
                ),
            )[0]
            if successful
            else None
        )
        all_summaries[game] = {
            "status": "TARGET_MET"
            if best and best["validation"]["row_within_tolerance"] >= budget.target_coverage
            else "TARGET_NOT_MET",
            "experiments": len(game_results),
            "successful": len(successful),
            "best": best,
            "protected_test_evaluated": False,
        }
    summary = {
        "schema_version": "1.0.0",
        "status": "TARGET_MET_ALL"
        if all(v.get("status") == "TARGET_MET" for v in all_summaries.values())
        else "TARGET_NOT_MET_ALL",
        "budget": asdict(budget),
        "games": all_summaries,
        "elapsed_seconds": time.time() - started,
        "note": (
            "Search is bounded; 'all settings' means every value "
            "explicitly enumerated in parameter_spaces, not an infinite "
            "continuum. Protected tests remain unopened."
        ),
    }
    atomic_write_json(output / "auto_research_summary.json", summary)
    return summary


def certify_auto_research(config_path: str | Path) -> dict[str, Any]:
    raw = _load_yaml(config_path)
    output = Path(raw.get("output", "runs/auto-coverage"))
    summary_path = output / "auto_research_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("run auto-coverage before certification")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    budget = SearchBudget(**raw.get("budget", {}))
    results: dict[str, Any] = {}
    for game, game_summary in summary.get("games", {}).items():
        best = game_summary.get("best")
        if not best or not best.get("candidate_artifact"):
            results[game] = {"status": "NO_CANDIDATE_SET"}
            continue
        data = _read_game_data(raw["games"][game]["input"], game)
        test_size = int(raw["games"][game].get("split", {}).get("test_size", 50))
        candidates_frame = pd.read_csv(best["candidate_artifact"])
        count, _ = GAME_GEOMETRY[game]
        candidates = [
            tuple(int(x) for x in row)
            for row in candidates_frame[[f"n{i}" for i in range(1, count + 1)]].to_numpy()
        ]
        evaluation = _evaluate_general(data[-test_size:], candidates, budget.tolerance)
        results[game] = {
            "status": "CERTIFIED_TARGET_MET"
            if evaluation["row_within_tolerance"] >= budget.target_coverage
            else "CERTIFIED_TARGET_NOT_MET",
            "evaluation": evaluation,
            "candidate_artifact": best["candidate_artifact"],
            "warning": "The protected test is now opened. Do not tune on this result.",
        }
    certification = {
        "schema_version": "1.0.0",
        "status": "CERTIFIED_TARGET_MET_ALL"
        if results and all(v.get("status") == "CERTIFIED_TARGET_MET" for v in results.values())
        else "CERTIFIED_TARGET_NOT_MET_ALL",
        "games": results,
    }
    atomic_write_json(output / "auto_coverage_certification.json", certification)
    return certification
