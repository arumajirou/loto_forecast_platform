from __future__ import annotations

import ast
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import GameGeometry, SplitContract


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def atomic_numpy(path: Path, writer: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as handle:
        writer(handle)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def discover_models(source_root: Path) -> list[dict[str, Any]]:
    models_dir = source_root / "models"
    if not models_dir.is_dir():
        raise FileNotFoundError(f"models directory not found: {models_dir}")
    inventory: list[dict[str, Any]] = []
    for path in sorted(models_dir.glob("*.py"), key=lambda item: item.name.casefold()):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        if "Model" not in classes:
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        inventory.append(
            {
                "model_name": path.stem,
                "path": path.relative_to(source_root).as_posix(),
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "top_level_imports": sorted(imports),
                "runtime_status": "EXECUTION_PENDING",
            }
        )
    if not inventory:
        raise RuntimeError("no models with class Model were discovered")
    return inventory


def validate_frame(
    frame: pd.DataFrame, geometry: GameGeometry, split: SplitContract
) -> dict[str, Any]:
    required = {
        geometry.draw_number_column,
        geometry.draw_date_column,
        *geometry.position_columns,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    if len(frame) < split.holdout_end_exclusive:
        raise ValueError("frame is shorter than holdout_end_exclusive")
    draw_numbers = pd.to_numeric(frame[geometry.draw_number_column], errors="raise")
    draw_dates = pd.to_datetime(frame[geometry.draw_date_column], errors="raise")
    if draw_numbers.duplicated().any() or not draw_numbers.is_monotonic_increasing:
        raise ValueError("draw numbers must be unique and time ordered")
    if draw_dates.duplicated().any() or not draw_dates.is_monotonic_increasing:
        raise ValueError("draw dates must be unique and time ordered")
    values = frame.loc[:, list(geometry.position_columns)].apply(
        pd.to_numeric, errors="raise"
    )
    array = values.to_numpy(dtype=float)
    if not np.isfinite(array).all():
        raise ValueError("position values must be finite")
    if (array < geometry.candidate_min).any() or (array > geometry.candidate_max).any():
        raise ValueError("position values fall outside GameGeometry bounds")
    return {
        "row_count": int(len(frame)),
        "first_draw_no": int(draw_numbers.iloc[0]),
        "last_draw_no": int(draw_numbers.iloc[-1]),
        "first_draw_date": draw_dates.iloc[0].isoformat(),
        "last_draw_date": draw_dates.iloc[-1].isoformat(),
        "position_count": len(geometry.position_columns),
    }


def materialize_training_bundle(
    frame: pd.DataFrame,
    geometry: GameGeometry,
    split: SplitContract,
    output_dir: Path,
) -> dict[str, Any]:
    validation = validate_frame(frame, geometry, split)
    output_dir.mkdir(parents=True, exist_ok=True)
    columns = [
        geometry.draw_date_column,
        geometry.draw_number_column,
        *geometry.position_columns,
    ]
    train = frame.iloc[: split.train_end_exclusive].loc[:, columns].copy()
    valid = frame.iloc[
        split.train_end_exclusive : split.validation_end_exclusive
    ].loc[:, columns].copy()
    train_path = output_dir / "train.csv"
    valid_path = output_dir / "validation.csv"
    train.to_csv(train_path, index=False)
    valid.to_csv(valid_path, index=False)
    manifest = {
        "status": "PASS",
        "geometry": geometry.model_dump(mode="json"),
        "split": split.model_dump(mode="json"),
        "validation": validation,
        "artifacts": {
            "train.csv": {"rows": len(train), "sha256": sha256_file(train_path)},
            "validation.csv": {"rows": len(valid), "sha256": sha256_file(valid_path)},
        },
        "excluded_by_contract": ["holdout", "prospective"],
    }
    atomic_write_json(output_dir / "manifest.json", manifest)
    return manifest
