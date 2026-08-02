from __future__ import annotations

import itertools
import os
import re
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from loto_ops.config import AppSettings

try:  # Optional fast path. The pandas fallback keeps the app usable before uv sync.
    import polars as pl
except Exception:  # pragma: no cover - environment dependent
    pl = None  # type: ignore[assignment]


TS_TYPES: tuple[str, ...] = (
    "raw",
    "cumsum",
    "roll3_sum",
    "roll7_mean",
    "diff1",
    "roll3_mean",
)

HIST_COLS: list[str] = [
    "hist_b1",
    "hist_pn1",
    "hist_pm1",
    "hist_pn2",
    "hist_pm2",
    "hist_pn3",
    "hist_pm3",
    "hist_pn4",
    "hist_pm4",
    "hist_b1_tens",
    "hist_b1_ones",
    "hist_pn5",
    "hist_pm5",
    "hist_co",
    "hist_b2",
    "hist_pn6",
    "hist_pm6",
    "hist_b2_tens",
    "hist_b2_ones",
    "hist_pn7",
    "hist_pm7",
    "hist_stc",
    "hist_stm",
    "hist_bxc",
    "hist_bxm",
    "hist_ssc",
    "hist_ssm",
    "hist_sbc",
    "hist_sbm",
    "hist_mnc",
    "hist_mnm",
]


@dataclass(frozen=True)
class FastBuildResult:
    sqlite_path: str
    rows: dict[str, int]
    artifacts: dict[str, str]
    engine: str
    seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "sqlite_path": self.sqlite_path,
            "rows": self.rows,
            "artifacts": self.artifacts,
            "engine": self.engine,
            "seconds": self.seconds,
        }


class FastDatasetBuilder:
    """Build loto_forecast-compatible datasets without the legacy PostgreSQL write path.

    The legacy upstream script is intentionally bypassed here because it can fall back to
    large pandas.to_sql INSERT statements. This builder owns only local artifacts:

    - SQLite: dataset_loto_y_ts, dataset_loto_hist_feat
    - CSV for PostgreSQL COPY
    - Optional Parquet artifacts for fast local analysis

    PostgreSQL loading is handled by CopyLoader/FastCopyLoader in the next stage.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.project = settings.paths.loto_life_project
        self.interim_dir = self.project / "data" / "interim"
        self.sqlite_path = settings.paths.sqlite_path
        self.postgres_load_dir = settings.paths.postgres_load_dir
        self.datasets_dir = settings.paths.datasets_dir
        self.fast_cfg = settings.raw.get("fast_mode", {})

    def run(self, *, engine: str = "auto", export_parquet: bool | None = None) -> dict[str, object]:
        started = time.perf_counter()
        self._configure_threads()
        use_polars = engine in {"auto", "polars"} and pl is not None
        if engine == "polars" and pl is None:
            raise RuntimeError(
                "polars is not installed. Run `uv sync` first or use --engine pandas."
            )

        if use_polars:
            yts, hist = self._build_with_polars()
            engine_name = "polars"
        else:
            yts, hist = self._build_with_pandas()
            engine_name = "pandas"

        export_parquet = bool(
            self.fast_cfg.get("export_parquet", True) if export_parquet is None else export_parquet
        )
        artifacts = self._write_outputs(yts, hist, export_parquet=export_parquet)
        rows = {
            "dataset_loto_y_ts": self._len(yts),
            "dataset_loto_hist_feat": self._len(hist),
        }
        return FastBuildResult(
            sqlite_path=str(self.sqlite_path),
            rows=rows,
            artifacts=artifacts,
            engine=engine_name,
            seconds=round(time.perf_counter() - started, 3),
        ).to_dict()

    def _configure_threads(self) -> None:
        threads = str(self.fast_cfg.get("polars_threads", self.fast_cfg.get("cpu_workers", 16)))
        os.environ.setdefault("POLARS_MAX_THREADS", threads)
        os.environ.setdefault("RAYON_NUM_THREADS", threads)
        # Keep BLAS from oversubscribing while Polars/PostgreSQL are doing the parallel work.
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("NUMEXPR_MAX_THREADS", str(self.fast_cfg.get("cpu_workers", 16)))

    @staticmethod
    def _len(frame: object) -> int:
        if pl is not None and isinstance(frame, pl.DataFrame):
            return int(frame.height)
        return len(frame)

    def _normalized_files(self) -> list[Path]:
        files = sorted(self.interim_dir.glob("*_normalized.csv"))
        if not files:
            raise FileNotFoundError(
                f"normalized CSV files not found: {self.interim_dir}. Run `loto-ops scrape` first."
            )
        return files

    @staticmethod
    def _read_csv_auto(path: Path) -> pd.DataFrame:
        for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
            try:
                return pd.read_csv(path, encoding=enc)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path, encoding_errors="replace")

    @staticmethod
    def _number_cols(columns: Iterable[str]) -> list[str]:
        cols = [str(c) for c in columns if re.fullmatch(r"[nd]\d+", str(c).lower())]
        return sorted(cols, key=lambda x: int(re.search(r"\d+", x).group(0)))

    @staticmethod
    def _bonus_cols(columns: Iterable[str]) -> list[str]:
        cols = [str(c) for c in columns if re.fullmatch(r"bonus\d+", str(c).lower())]
        return sorted(cols, key=lambda x: int(re.search(r"\d+", x).group(0)))

    def _build_with_polars(self):
        assert pl is not None
        base_parts: list[pl.DataFrame] = []
        hist_draw_parts: list[pl.DataFrame] = []
        now = pd.Timestamp.utcnow().tz_localize(None)

        for path in self._normalized_files():
            game = path.stem.replace("_normalized", "")
            pdf = self._read_csv_auto(path)
            if "draw_date" not in pdf.columns:
                continue
            ncols = self._number_cols(pdf.columns)
            if not ncols:
                continue

            # Polars receives pandas here to avoid CSV encoding edge cases.
            df = pl.from_pandas(pdf)
            df = df.with_columns(
                pl.lit(game).alias("loto"),
                pl.col("draw_date").cast(pl.Utf8).str.to_date(strict=False).alias("ds"),
            )
            melted = df.select(["loto", "ds", *ncols]).unpivot(
                index=["loto", "ds"],
                on=ncols,
                variable_name="position",
                value_name="base_y",
            )
            melted = (
                melted.with_columns(
                    pl.col("position")
                    .str.extract(r"(\d+)")
                    .cast(pl.Int64)
                    .map_elements(lambda x: f"N{x}", return_dtype=pl.Utf8)
                    .alias("unique_id"),
                    pl.col("base_y").cast(pl.Float64, strict=False),
                    pl.lit(now).alias("exec_ts"),
                    pl.lit(now).alias("updated_ts"),
                    pl.lit(0.0).alias("proc_seconds"),
                )
                .drop("position")
                .drop_nulls(["ds", "base_y"])
            )
            base_parts.append(melted)
            hist_draw_parts.append(pl.from_pandas(self._draw_level_hist_features_pandas(path)))

        if not base_parts:
            raise RuntimeError("No normalized rows were converted to base dataset.")

        base = pl.concat(base_parts).sort(["loto", "unique_id", "ds"])
        yts_parts: list[pl.DataFrame] = []
        raw = base.with_columns(pl.lit("raw").alias("ts_type"), pl.col("base_y").alias("y"))
        yts_parts.append(raw)
        yts_parts.append(
            base.with_columns(
                pl.lit("cumsum").alias("ts_type"),
                pl.col("base_y").cum_sum().over(["loto", "unique_id"]).alias("y"),
            )
        )
        yts_parts.append(
            base.with_columns(
                pl.lit("diff1").alias("ts_type"),
                pl.col("base_y").diff().over(["loto", "unique_id"]).alias("y"),
            )
        )
        yts_parts.append(
            base.with_columns(
                pl.lit("roll3_sum").alias("ts_type"),
                pl.col("base_y")
                .rolling_sum(window_size=3, min_samples=1)
                .over(["loto", "unique_id"])
                .alias("y"),
            )
        )
        yts_parts.append(
            base.with_columns(
                pl.lit("roll3_mean").alias("ts_type"),
                pl.col("base_y")
                .rolling_mean(window_size=3, min_samples=1)
                .over(["loto", "unique_id"])
                .alias("y"),
            )
        )
        yts_parts.append(
            base.with_columns(
                pl.lit("roll7_mean").alias("ts_type"),
                pl.col("base_y")
                .rolling_mean(window_size=7, min_samples=1)
                .over(["loto", "unique_id"])
                .alias("y"),
            )
        )
        yts = (
            pl.concat(yts_parts)
            .select(
                ["loto", "ds", "unique_id", "ts_type", "y", "exec_ts", "updated_ts", "proc_seconds"]
            )
            .sort(["loto", "unique_id", "ts_type", "ds"])
        )

        draw_hist = pl.concat(hist_draw_parts)
        keys = base.select(["loto", "ds", "unique_id"]).unique()
        hist = keys.join(draw_hist, on=["loto", "ds"], how="left")
        for col in HIST_COLS:
            if col not in hist.columns:
                hist = hist.with_columns(pl.lit(None, dtype=pl.Float64).alias(col))
        hist = hist.with_columns(
            pl.lit(now).alias("exec_ts"),
            pl.lit(now).alias("updated_ts"),
            pl.lit(0.0).alias("proc_seconds"),
        ).select(["loto", "ds", "unique_id", *HIST_COLS, "exec_ts", "updated_ts", "proc_seconds"])
        return yts, hist.sort(["loto", "unique_id", "ds"])

    def _build_with_pandas(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        rows: list[pd.DataFrame] = []
        now = pd.Timestamp.utcnow().tz_localize(None)
        for path in self._normalized_files():
            game = path.stem.replace("_normalized", "")
            df = self._read_csv_auto(path)
            if "draw_date" not in df.columns:
                continue
            df["ds"] = pd.to_datetime(df["draw_date"], errors="coerce").dt.date
            for pos, col in enumerate(self._number_cols(df.columns), start=1):
                rows.append(
                    pd.DataFrame(
                        {
                            "loto": game,
                            "ds": df["ds"],
                            "unique_id": f"N{pos}",
                            "base_y": pd.to_numeric(df[col], errors="coerce"),
                            "exec_ts": now,
                            "updated_ts": now,
                            "proc_seconds": 0.0,
                        }
                    )
                )
        if not rows:
            raise RuntimeError("No normalized rows were converted to base dataset.")
        base = pd.concat(rows, ignore_index=True).dropna(subset=["ds", "base_y"])
        base = base.sort_values(["loto", "unique_id", "ds"]).reset_index(drop=True)

        yts_frames: list[pd.DataFrame] = []
        for _, g in base.groupby(["loto", "unique_id"], sort=False):
            g = g.sort_values("ds").copy()
            y = g["base_y"].astype(float)
            derived = {
                "raw": y,
                "cumsum": y.cumsum(),
                "roll3_sum": y.rolling(3, min_periods=1).sum(),
                "roll7_mean": y.rolling(7, min_periods=1).mean(),
                "diff1": y.diff(1),
                "roll3_mean": y.rolling(3, min_periods=1).mean(),
            }
            for ts_type, values in derived.items():
                out = g[["loto", "ds", "unique_id", "exec_ts", "updated_ts", "proc_seconds"]].copy()
                out["ts_type"] = ts_type
                out["y"] = values.to_numpy(dtype=float)
                yts_frames.append(out)
        yts = pd.concat(yts_frames, ignore_index=True)[
            ["loto", "ds", "unique_id", "ts_type", "y", "exec_ts", "updated_ts", "proc_seconds"]
        ]
        draw_hist = pd.concat(
            [self._draw_level_hist_features_pandas(p) for p in self._normalized_files()],
            ignore_index=True,
        )
        keys = base[["loto", "ds", "unique_id"]].drop_duplicates()
        hist = keys.merge(draw_hist, on=["loto", "ds"], how="left")
        for col in HIST_COLS:
            if col not in hist.columns:
                hist[col] = pd.NA
        hist["exec_ts"] = now
        hist["updated_ts"] = now
        hist["proc_seconds"] = 0.0
        hist = hist[
            ["loto", "ds", "unique_id", *HIST_COLS, "exec_ts", "updated_ts", "proc_seconds"]
        ]
        return yts.sort_values(["loto", "unique_id", "ts_type", "ds"]), hist.sort_values(
            ["loto", "unique_id", "ds"]
        )

    def _draw_level_hist_features_pandas(self, path: Path) -> pd.DataFrame:
        game = path.stem.replace("_normalized", "")
        df = self._read_csv_auto(path).copy()
        df["loto"] = game
        df["ds"] = pd.to_datetime(df["draw_date"], errors="coerce").dt.date
        ncols = self._number_cols(df.columns)
        bcols = self._bonus_cols(df.columns)
        nums = (
            df[ncols].apply(pd.to_numeric, errors="coerce")
            if ncols
            else pd.DataFrame(index=df.index)
        )
        out = pd.DataFrame({"loto": df["loto"], "ds": df["ds"]})

        for i in range(1, 8):
            col = f"n{i}"
            if col in df.columns:
                v = pd.to_numeric(df[col], errors="coerce").astype("float64")
            else:
                v = pd.Series(np.nan, index=df.index, dtype="float64")
            out[f"hist_pn{i}"] = v.shift(1)
            out[f"hist_pm{i}"] = v.expanding().mean().shift(1)

        b1 = (
            pd.to_numeric(df[bcols[0]], errors="coerce").astype("float64")
            if len(bcols) >= 1
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )
        b2 = (
            pd.to_numeric(df[bcols[1]], errors="coerce").astype("float64")
            if len(bcols) >= 2
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )
        out["hist_b1"] = b1.shift(1)
        out["hist_b2"] = b2.shift(1)
        out["hist_b1_tens"] = (out["hist_b1"] // 10).astype("float64")
        out["hist_b1_ones"] = out["hist_b1"] % 10
        out["hist_b2_tens"] = (out["hist_b2"] // 10).astype("float64")
        out["hist_b2_ones"] = out["hist_b2"] % 10

        if nums.empty:
            draw_sum = pd.Series(np.nan, index=df.index, dtype="float64")
            odd_count = pd.Series(np.nan, index=df.index, dtype="float64")
            min_n = pd.Series(np.nan, index=df.index, dtype="float64")
            max_n = pd.Series(np.nan, index=df.index, dtype="float64")
            spread = pd.Series(np.nan, index=df.index, dtype="float64")
            consecutive_count = pd.Series(np.nan, index=df.index, dtype="float64")
        else:
            nums = nums.astype("float64")
            draw_sum = nums.sum(axis=1).astype("float64")
            odd_count = nums.mod(2).sum(axis=1).astype("float64")
            min_n = nums.min(axis=1).astype("float64")
            max_n = nums.max(axis=1).astype("float64")
            spread = (max_n - min_n).astype("float64")
            consecutive_count = nums.apply(self._consecutive_count, axis=1).astype("float64")

        out["hist_co"] = consecutive_count.shift(1)
        out["hist_stc"] = draw_sum.shift(1)
        out["hist_stm"] = draw_sum.expanding().mean().shift(1)
        out["hist_bxc"] = max_n.shift(1)
        out["hist_bxm"] = max_n.expanding().mean().shift(1)
        out["hist_ssc"] = spread.shift(1)
        out["hist_ssm"] = spread.expanding().mean().shift(1)
        out["hist_sbc"] = odd_count.shift(1)
        out["hist_sbm"] = odd_count.expanding().mean().shift(1)
        out["hist_mnc"] = min_n.shift(1)
        out["hist_mnm"] = min_n.expanding().mean().shift(1)
        for c in HIST_COLS:
            if c not in out.columns:
                out[c] = np.nan
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")
        return out[["loto", "ds", *HIST_COLS]]

    @staticmethod
    def _consecutive_count(row: pd.Series) -> int:
        vals = sorted(int(x) for x in row.dropna().tolist())
        return sum(1 for a, b in itertools.pairwise(vals) if b - a == 1)

    def _write_outputs(self, yts, hist, *, export_parquet: bool) -> dict[str, str]:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.postgres_load_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, str] = {}

        if pl is not None and isinstance(yts, pl.DataFrame):
            yts_pd = yts.to_pandas()
            hist_pd = hist.to_pandas()
            if export_parquet:
                yts_parquet = self.datasets_dir / "dataset_loto_y_ts.parquet"
                hist_parquet = self.datasets_dir / "dataset_loto_hist_feat.parquet"
                yts.write_parquet(yts_parquet)
                hist.write_parquet(hist_parquet)
                artifacts["yts_parquet"] = str(yts_parquet)
                artifacts["hist_parquet"] = str(hist_parquet)
        else:
            yts_pd = yts
            hist_pd = hist
            if export_parquet:
                yts_parquet = self.datasets_dir / "dataset_loto_y_ts.parquet"
                hist_parquet = self.datasets_dir / "dataset_loto_hist_feat.parquet"
                yts_pd.to_parquet(yts_parquet, index=False)
                hist_pd.to_parquet(hist_parquet, index=False)
                artifacts["yts_parquet"] = str(yts_parquet)
                artifacts["hist_parquet"] = str(hist_parquet)

        with sqlite3.connect(self.sqlite_path) as conn:
            yts_pd.to_sql("dataset_loto_y_ts", conn, if_exists="replace", index=False)
            hist_pd.to_sql("dataset_loto_hist_feat", conn, if_exists="replace", index=False)
        artifacts["sqlite"] = str(self.sqlite_path)

        yts_csv = self.postgres_load_dir / "loto_y_ts.csv"
        hist_csv = self.postgres_load_dir / "loto_hist_feat.csv"
        yts_pd.to_csv(yts_csv, index=False, encoding="utf-8")
        hist_pd.to_csv(hist_csv, index=False, encoding="utf-8")
        artifacts["yts_csv"] = str(yts_csv)
        artifacts["hist_csv"] = str(hist_csv)
        return artifacts
