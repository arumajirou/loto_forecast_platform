from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contracts import CampaignConfig


@dataclass(frozen=True)
class DataContract:
    rows: int
    draws: int
    first_draw_index: int
    last_draw_index: int
    number_columns: tuple[str, ...]
    draw_id_column: str
    draw_index_column: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "draws": self.draws,
            "first_draw_index": self.first_draw_index,
            "last_draw_index": self.last_draw_index,
            "number_columns": list(self.number_columns),
            "draw_id_column": self.draw_id_column,
            "draw_index_column": self.draw_index_column,
        }


def _resolve_column(columns: Iterable[str], candidates: list[str], *, label: str) -> str:
    available = list(columns)
    lowered = {str(column).lower(): str(column) for column in available}
    for candidate in candidates:
        if candidate in available:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    raise ValueError(f"{label} column not found; candidates={candidates}, available={available}")


def _normalize_column_name(name: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _resolve_number_columns(
    columns: Iterable[object],
    expected_columns: Iterable[object],
) -> tuple[list[str], dict[str, str]]:
    available = [str(column) for column in columns]
    expected = [str(column) for column in expected_columns]
    normalized = {_normalize_column_name(column): column for column in available}

    candidate_groups: list[list[str]] = [
        expected,
        [f"n{index}" for index in range(1, len(expected) + 1)],
        [f"num{index}" for index in range(1, len(expected) + 1)],
        [f"number{index}" for index in range(1, len(expected) + 1)],
        [f"position{index}" for index in range(1, len(expected) + 1)],
        [f"p{index}" for index in range(1, len(expected) + 1)],
    ]

    for group in candidate_groups:
        keys = [_normalize_column_name(name) for name in group]
        if all(key in normalized for key in keys):
            source = [normalized[key] for key in keys]
            return source, dict(zip(expected, source, strict=True))

    raise ValueError(
        f"Mini Loto number columns not found; expected={expected}, available={available}"
    )


def load_miniloto(config: CampaignConfig) -> tuple[pd.DataFrame, DataContract]:
    path = config.data_path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    source_number_columns, number_column_mapping = _resolve_number_columns(
        frame.columns,
        config.number_columns,
    )
    number_columns = [str(column) for column in config.number_columns]
    draw_id = _resolve_column(frame.columns, config.draw_id_candidates, label="draw_id")
    try:
        draw_index = _resolve_column(
            frame.columns, config.draw_index_candidates, label="draw_index"
        )  # noqa: E501
    except ValueError:
        draw_index = "__draw_index__"
        frame[draw_index] = np.arange(1, len(frame) + 1, dtype=np.int64)

    selected_columns = list(dict.fromkeys([draw_id, draw_index, *source_number_columns]))
    if draw_index == draw_id:
        source_draw_index = pd.to_numeric(
            frame[draw_index],
            errors="raise",
        ).astype("int64")
        draw_index = "__draw_index__"
        frame[draw_index] = source_draw_index

    selected_columns = list(dict.fromkeys([draw_id, draw_index, *source_number_columns]))
    missing_selected_columns = [
        column for column in selected_columns if column not in frame.columns
    ]
    if missing_selected_columns:
        raise ValueError(f"selected Mini Loto columns missing: {missing_selected_columns}")
    normalized = frame.loc[:, selected_columns].copy()
    normalized = normalized.rename(
        columns={source: canonical for canonical, source in number_column_mapping.items()}
    )
    normalized[draw_id] = normalized[draw_id].astype("string")
    normalized[draw_index] = pd.to_numeric(normalized[draw_index], errors="raise").astype("int64")
    for column in number_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise")
        if normalized[column].isna().any() or not np.isfinite(normalized[column]).all():
            raise ValueError(f"non-finite values in {column}")
    normalized = normalized.sort_values(draw_index, kind="stable").reset_index(drop=True)
    if normalized[draw_index].duplicated().any():
        raise ValueError("duplicate draw_index values")
    if normalized[draw_id].duplicated().any():
        raise ValueError("duplicate draw_id values")
    if not normalized[draw_index].is_monotonic_increasing:
        raise ValueError("draw_index order violation")

    contract = DataContract(
        rows=len(normalized),
        draws=len(normalized),
        first_draw_index=int(normalized[draw_index].iloc[0]),
        last_draw_index=int(normalized[draw_index].iloc[-1]),
        number_columns=tuple(number_columns),
        draw_id_column=draw_id,
        draw_index_column=draw_index,
    )
    return normalized, contract


def build_panel(
    frame: pd.DataFrame, contract: DataContract, *, track: str, position: int | None = None
) -> pd.DataFrame:  # noqa: E501
    id_col = contract.draw_id_column
    index_col = contract.draw_index_column
    columns = list(contract.number_columns)
    if track == "u_local":
        if position is None or not 1 <= position <= len(columns):
            raise ValueError("u_local requires a valid position")
        column = columns[position - 1]
        return pd.DataFrame(
            {
                "unique_id": column,
                "ds": frame[index_col].astype("int64"),
                "y": frame[column].astype(float),
                "draw_id": frame[id_col].astype("string"),
                "draw_index": frame[index_col].astype("int64"),
            }
        )
    parts = []
    for column in columns:
        parts.append(
            pd.DataFrame(
                {
                    "unique_id": column,
                    "ds": frame[index_col].astype("int64"),
                    "y": frame[column].astype(float),
                    "draw_id": frame[id_col].astype("string"),
                    "draw_index": frame[index_col].astype("int64"),
                }
            )
        )
    if track == "h_hint":
        parts.insert(
            0,
            pd.DataFrame(
                {
                    "unique_id": "TOTAL",
                    "ds": frame[index_col].astype("int64"),
                    "y": frame[columns].sum(axis=1).astype(float),
                    "draw_id": frame[id_col].astype("string"),
                    "draw_index": frame[index_col].astype("int64"),
                }
            ),
        )
    return pd.concat(parts, ignore_index=True)


def hint_summing_matrix(n_bottom: int = 5) -> np.ndarray:
    return np.vstack([np.ones((1, n_bottom), dtype=float), np.eye(n_bottom, dtype=float)])


def pre_holdout_frame(frame: pd.DataFrame, config: CampaignConfig) -> pd.DataFrame:
    stop = len(frame) - config.split.holdout_draws
    if stop <= config.split.validation_draws:
        raise ValueError("insufficient draws for train/validation/holdout")
    return frame.iloc[:stop].copy()


def holdout_origins(frame: pd.DataFrame, config: CampaignConfig) -> list[int]:
    start = len(frame) - config.split.holdout_draws
    return list(range(start, len(frame)))


def oof_endpoints(frame: pd.DataFrame, config: CampaignConfig) -> list[int]:
    """Return expanding-window origins strictly inside the Train partition.

    Validation and Holdout must never be used by OOF. An endpoint is the index of
    the one-step actual, so the maximum endpoint is ``train_stop - 1``.
    """

    train_stop = len(frame) - config.split.holdout_draws - config.split.validation_draws
    minimum = max(20, train_stop // 2)
    maximum = train_stop - 1
    if minimum >= maximum:
        raise ValueError("insufficient Train-only data for OOF")
    endpoints = np.linspace(
        minimum,
        maximum,
        config.split.oof_folds,
        dtype=int,
    )
    unique = sorted(set(int(value) for value in endpoints))
    if len(unique) != config.split.oof_folds:
        raise ValueError("OOF endpoints are not unique; increase Train size")
    if any(value >= train_stop for value in unique):
        raise AssertionError("OOF endpoint escaped the Train partition")
    return unique


def oof_origins(
    frame: pd.DataFrame,
    config: CampaignConfig,
) -> list[tuple[int, int]]:
    """Return dense Train-only expanding-window origins with fold labels."""

    train_stop = len(frame) - config.split.holdout_draws - config.split.validation_draws
    minimum = max(20, train_stop // 2)
    maximum = train_stop - 1
    total = config.split.oof_folds * config.split.oof_origins_per_fold
    if minimum >= maximum or total < 1:
        raise ValueError("insufficient Train-only data for dense OOF")
    values = np.linspace(minimum, maximum, total, dtype=int)
    unique = [int(value) for value in values]
    if len(set(unique)) != total:
        raise ValueError("dense OOF origins are not unique; reduce oof_origins_per_fold")
    if any(value >= train_stop for value in unique):
        raise AssertionError("dense OOF origin escaped the Train partition")
    rows: list[tuple[int, int]] = []
    for index, origin in enumerate(unique):
        fold = index // config.split.oof_origins_per_fold + 1
        rows.append((fold, origin))
    return rows
