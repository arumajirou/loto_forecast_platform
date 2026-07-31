"""Deterministic, leakage-safe candidate feature generation."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from loto.contracts import FeatureSetManifest
from loto.data.canonical import NUMBER_COLS


def _selection_matrix(master: pd.DataFrame) -> np.ndarray:
    matrix = np.zeros((len(master), 37), dtype=np.float64)
    for row_idx, row in enumerate(master[NUMBER_COLS].itertuples(index=False, name=None)):
        matrix[row_idx, np.asarray(row, dtype=int) - 1] = 1.0
    return matrix


def _feature_rows_for_index(
    *,
    selected: np.ndarray,
    idx: int,
    windows: tuple[int, ...],
    last_seen: np.ndarray,
    exp_num: np.ndarray,
    exp_den: float,
) -> dict[str, np.ndarray]:
    hist_len = idx
    result: dict[str, np.ndarray] = {}
    for window in windows:
        start = max(0, idx - window)
        denom = idx - start
        result[f"freq_w{window}"] = (
            selected[start:idx].mean(axis=0) if denom > 0 else np.zeros(37, dtype=float)
        )
    result["freq_all"] = selected[:idx].mean(axis=0) if hist_len > 0 else np.zeros(37, dtype=float)
    result["gap_draws"] = np.where(last_seen >= 0, idx - last_seen, idx + 1).astype(float)
    result["freq_exp"] = exp_num / exp_den if exp_den > 0 else np.zeros(37, dtype=float)
    candidates = np.arange(1, 38, dtype=float)
    result["candidate_scaled"] = candidates / 37.0
    result["candidate_is_even"] = (candidates % 2 == 0).astype(float)
    result["candidate_mod3"] = candidates % 3
    result["candidate_mod10"] = candidates % 10
    result["candidate_is_prime"] = np.asarray(
        [int(n >= 2 and all(n % d for d in range(2, int(n**0.5) + 1))) for n in range(1, 38)],
        dtype=float,
    )
    return result


def build_candidate_features(
    master: pd.DataFrame, windows: tuple[int, ...] = (10, 30, 100)
) -> pd.DataFrame:
    selected = _selection_matrix(master)
    rows: list[dict] = []
    last_seen = np.full(37, -1, dtype=int)
    exp_num = np.zeros(37, dtype=float)
    exp_den = 0.0
    decay = 0.95

    for idx, current in master.reset_index(drop=True).iterrows():
        arrays = _feature_rows_for_index(
            selected=selected,
            idx=idx,
            windows=windows,
            last_seen=last_seen,
            exp_num=exp_num,
            exp_den=exp_den,
        )
        for candidate in range(1, 38):
            row = {
                "draw_id": current["draw_id"],
                "draw_no": int(current["draw_no"]),
                "draw_date": current["draw_date"],
                "candidate_number": candidate,
                "selected": int(selected[idx, candidate - 1]),
            }
            row.update({name: float(values[candidate - 1]) for name, values in arrays.items()})
            rows.append(row)

        # Update state only after all features for the current draw have been emitted.
        current_vec = selected[idx]
        exp_num = decay * exp_num + current_vec
        exp_den = decay * exp_den + 1.0
        last_seen[current_vec.astype(bool)] = idx

    return pd.DataFrame(rows)


def build_next_candidate_features(
    master: pd.DataFrame, windows: tuple[int, ...] = (10, 30, 100)
) -> pd.DataFrame:
    selected = _selection_matrix(master)
    idx = len(master)
    last_seen = np.full(37, -1, dtype=int)
    for draw_idx, row in enumerate(selected):
        last_seen[row.astype(bool)] = draw_idx
    decay = 0.95
    if idx:
        powers = decay ** np.arange(idx - 1, -1, -1, dtype=float)
        exp_num = powers @ selected
        exp_den = float(powers.sum())
    else:
        exp_num = np.zeros(37, dtype=float)
        exp_den = 0.0
    arrays = _feature_rows_for_index(
        selected=selected,
        idx=idx,
        windows=windows,
        last_seen=last_seen,
        exp_num=np.asarray(exp_num, dtype=float),
        exp_den=exp_den,
    )
    next_draw = int(master["draw_no"].max()) + 1
    rows: list[dict] = []
    for candidate in range(1, 38):
        row = {
            "draw_id": f"loto7-{next_draw}",
            "draw_no": next_draw,
            "candidate_number": candidate,
        }
        row.update({name: float(values[candidate - 1]) for name, values in arrays.items()})
        rows.append(row)
    return pd.DataFrame(rows)


def feature_manifest(
    features: pd.DataFrame, data_version: str, windows: tuple[int, ...]
) -> FeatureSetManifest:
    payload = features.to_json(orient="records", date_format="iso")
    sha = hashlib.sha256(payload.encode()).hexdigest()
    return FeatureSetManifest(
        feature_set_id=f"candidate-v1-{sha[:12]}",
        data_version=data_version,
        row_count=len(features),
        windows=list(windows),
        sha256=sha,
    )
