from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fold:
    fold_id: str
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def rolling_folds(n_rows: int, *, folds: int, test_size: int, min_train_size: int,
                  gap: int = 0, expanding: bool = True) -> list[Fold]:
    required = min_train_size + gap + test_size
    if n_rows < required:
        return []
    latest_test_end = n_rows
    values: list[Fold] = []
    for reverse_index in range(folds):
        test_end = latest_test_end - reverse_index * test_size
        test_start = test_end - test_size
        train_end = test_start - gap
        if train_end < min_train_size:
            break
        train_start = 0 if expanding else max(0, train_end - min_train_size)
        values.append(Fold(
            fold_id=f"fold-{folds - reverse_index:02d}",
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        ))
    return list(reversed(values))


def split_development_holdout(n_rows: int, holdout_size: int) -> tuple[slice, slice]:
    if holdout_size <= 0:
        return slice(0, n_rows), slice(n_rows, n_rows)
    if n_rows <= holdout_size:
        raise ValueError("dataset is not large enough for configured holdout")
    boundary = n_rows - holdout_size
    return slice(0, boundary), slice(boundary, n_rows)
