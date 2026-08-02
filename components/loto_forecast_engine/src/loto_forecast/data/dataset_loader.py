from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .db import read_timeseries


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _to_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _normalize_loader_name(value: Any) -> str:
    name = str(value or "db_table").strip().lower().replace("-", "_")
    aliases = {
        "postgres": "db_table",
        "postgresql": "db_table",
        "db": "db_table",
        "table": "db_table",
        "query": "sql",
        "ndjson": "jsonl",
    }
    return aliases.get(name, name)


def _normalize_backend_name(value: Any) -> str:
    name = str(value or "pandas").strip().lower()
    return name if name in {"pandas", "polars", "dask", "spark"} else "pandas"


def _resolve_input_paths(loader: str, source: str, *, load_all: bool) -> list[Path]:
    _ = loader
    expanded = Path(source).expanduser()
    raw = str(expanded)
    if any(ch in raw for ch in "*?["):
        paths = [Path(item).resolve() for item in glob.glob(raw, recursive=True) if Path(item).is_file()]
    elif expanded.is_file():
        paths = [expanded.resolve()]
    elif expanded.is_dir():
        suffixes = {".csv", ".parquet", ".json", ".jsonl", ".ndjson", ".feather"}
        paths = [p.resolve() for p in expanded.rglob("*") if p.is_file() and p.suffix.lower() in suffixes]
    else:
        paths = []
    paths = sorted(dict.fromkeys(paths))
    return paths if load_all else paths[:1]


def _read_one_with_pandas(path: Path, loader: str, options: dict[str, Any]) -> pd.DataFrame:
    loader = _normalize_loader_name(loader)
    if loader == "csv":
        return pd.read_csv(path, **options)
    if loader == "parquet":
        return pd.read_parquet(path, **options)
    if loader in {"jsonl", "json"}:
        lines = loader == "jsonl" or path.suffix.lower() in {".jsonl", ".ndjson"}
        return pd.read_json(path, lines=lines, **options)
    if loader == "feather":
        return pd.read_feather(path, **options)
    raise ValueError(f"unsupported dataset loader: {loader}")


def _read_file_dataset(
    loader: str,
    backend: str,
    source: str,
    load_all: bool,
    options: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    paths = _resolve_input_paths(loader, source, load_all=load_all)
    if not paths:
        raise FileNotFoundError(f"dataset input not found: {source}")
    options = dict(options or {})
    requested = _normalize_backend_name(backend)
    warnings: list[str] = []
    frames: list[pd.DataFrame] = []
    used = requested
    try:
        if requested == "polars":
            import polars as pl

            for path in paths:
                if loader == "csv":
                    frames.append(pl.read_csv(path, **options).to_pandas())
                elif loader == "parquet":
                    frames.append(pl.read_parquet(path, **options).to_pandas())
                else:
                    raise ValueError(f"polars backend does not support {loader}")
        elif requested == "dask":
            import dask.dataframe as dd

            for path in paths:
                if loader == "csv":
                    frames.append(dd.read_csv(str(path), **options).compute())
                elif loader == "parquet":
                    frames.append(dd.read_parquet(str(path), **options).compute())
                else:
                    raise ValueError(f"dask backend does not support {loader}")
        elif requested == "spark":
            used = "pandas"
            warnings.append("backend=spark not enabled in the compatibility loader; used pandas")
            frames = [_read_one_with_pandas(path, loader, options) for path in paths]
        else:
            used = "pandas"
            frames = [_read_one_with_pandas(path, loader, options) for path in paths]
    except ImportError as exc:
        used = "pandas"
        warnings.append(f"backend={requested} unavailable ({exc}); used pandas")
        frames = [_read_one_with_pandas(path, loader, options) for path in paths]
    except Exception as exc:
        raise RuntimeError(f"failed to read dataset file: {exc}") from exc

    frame = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    return frame, {
        "loader": loader,
        "backend_requested": requested,
        "backend_used": used,
        "source_count": len(paths),
        "sources": [str(path) for path in paths],
        "warnings": warnings,
    }


def load_dataset_from_settings(
    engine: Any,
    params: dict[str, Any],
    *,
    default_schema: str,
    default_table: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    loader = _normalize_loader_name(params.get("dataset_loader", "db_table"))
    if loader == "db_table":
        schema = str(params.get("dataset_schema") or default_schema)
        table = str(params.get("dataset_table") or default_table)
        frame = read_timeseries(engine, schema, table, where_sql=params.get("dataset_where"))
        return frame, {"loader": loader, "label": f"{schema}.{table}"}
    if loader == "sql":
        sql = str(params.get("dataset_sql") or "").strip()
        if not sql:
            raise ValueError("dataset_loader=sql requires dataset_sql")
        sql_params = _to_json_dict(params.get("dataset_sql_params"))
        return pd.read_sql(sql, engine, params=sql_params), {"loader": loader, "label": "sql_query"}

    source = str(params.get("dataset_path") or "").strip()
    if not source:
        raise ValueError(f"dataset_loader={loader} requires dataset_path")
    return _read_file_dataset(
        loader=loader,
        backend=_normalize_backend_name(params.get("dataset_backend", "pandas")),
        source=source,
        load_all=_to_bool(params.get("dataset_load_all"), False),
        options=_to_json_dict(params.get("dataset_read_options")),
    )
