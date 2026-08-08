from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.toto2_campaign.certification_bundle import sha256_file
from loto.toto2_campaign.geometry import GameGeometry, geometry_for_game
from loto.toto2_campaign.model_manifest import (
    MODEL_ID,
    MODEL_LICENSE,
    MODEL_REVISION,
    REPO_ID,
    SOURCE_REVISION,
)

FORMAL_CONTEXTS = (128, 256, 512)
FORMAL_HORIZONS = (1, 2, 5)
FORMAL_DEVICES = ("cpu", "cuda")
FORMAL_GAMES = ("numbers3", "numbers4", "miniloto", "loto6", "loto7")
_SAFE_COLUMN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


@dataclass(frozen=True)
class HistoryRow:
    draw_no: int
    values: dict[str, float]


@dataclass(frozen=True)
class HistoryExport:
    game_id: str
    position_columns: tuple[str, ...]
    rows: tuple[HistoryRow, ...]
    source_path: Path
    source_sha256: str

    @property
    def last_draw_no(self) -> int:
        return self.rows[-1].draw_no


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"history export root must be an object: {path}")
    return payload


def _validate_columns(columns: Any, geometry: GameGeometry) -> tuple[str, ...]:
    if not isinstance(columns, list) or len(columns) != geometry.position_count:
        raise ValueError(f"position_columns must contain {geometry.position_count} names")
    normalized = tuple(columns)
    if len(set(normalized)) != len(normalized):
        raise ValueError("position_columns must be unique")
    for column in normalized:
        if not isinstance(column, str) or not _SAFE_COLUMN.fullmatch(column):
            raise ValueError(f"unsafe position column: {column!r}")
    return normalized


def _validate_values(
    values: Any,
    columns: tuple[str, ...],
    geometry: GameGeometry,
    row_index: int,
) -> dict[str, float]:
    if not isinstance(values, dict) or set(values) != set(columns):
        raise ValueError(f"row {row_index} values do not match position_columns")
    normalized: dict[str, float] = {}
    ordered: list[float] = []
    for column in columns:
        value = values[column]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"row {row_index} has non-numeric value: {column}")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"row {row_index} has non-finite value: {column}")
        if not numeric.is_integer():
            raise ValueError(f"row {row_index} has non-integer value: {column}")
        integer = int(numeric)
        if not geometry.candidate_min <= integer <= geometry.candidate_max:
            raise ValueError(f"row {row_index} value outside game domain: {column}")
        normalized[column] = float(integer)
        ordered.append(float(integer))
    if geometry.strictly_increasing:
        if any(current <= previous for previous, current in zip(ordered, ordered[1:])):
            raise ValueError(f"row {row_index} positions must be strictly increasing")
    return normalized


def load_history_export(path: Path) -> HistoryExport:
    payload = _load_object(path)
    allowed = {"schema_version", "game_id", "position_columns", "rows"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"history export contains unknown fields: {unknown}")
    if payload.get("schema_version") != 1:
        raise ValueError("history export schema_version must be 1")
    game_id = payload.get("game_id")
    if not isinstance(game_id, str):
        raise ValueError("history export game_id must be a string")
    geometry = geometry_for_game(game_id)
    columns = _validate_columns(payload.get("position_columns"), geometry)
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) < max(FORMAL_CONTEXTS):
        raise ValueError("history export must contain at least 512 rows")

    rows: list[HistoryRow] = []
    previous_draw: int | None = None
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict) or set(raw_row) != {"draw_no", "values"}:
            raise ValueError(f"row {index} must contain only draw_no and values")
        draw_no = raw_row["draw_no"]
        if isinstance(draw_no, bool) or not isinstance(draw_no, int) or draw_no < 1:
            raise ValueError(f"row {index} draw_no must be a positive integer")
        if previous_draw is not None and draw_no != previous_draw + 1:
            raise ValueError("draw_no must be strictly increasing and gap-free")
        values = _validate_values(raw_row["values"], columns, geometry, index)
        rows.append(HistoryRow(draw_no=draw_no, values=values))
        previous_draw = draw_no

    return HistoryExport(
        game_id=game_id,
        position_columns=columns,
        rows=tuple(rows),
        source_path=path,
        source_sha256=sha256_file(path),
    )


def build_request(
    history: HistoryExport,
    *,
    context: int,
    horizon: int,
    device: str,
    snapshot_path: Path,
) -> dict[str, Any]:
    if context not in FORMAL_CONTEXTS:
        raise ValueError(f"unsupported formal context: {context}")
    if horizon not in FORMAL_HORIZONS:
        raise ValueError(f"unsupported formal horizon: {horizon}")
    if device not in FORMAL_DEVICES:
        raise ValueError(f"unsupported formal device: {device}")
    selected = history.rows[-context:]
    case_id = f"{history.game_id}-c{context}-h{horizon}-{device}"
    geometry = geometry_for_game(history.game_id)
    return {
        "schema_version": 2,
        "run_id": (f"toto2-4m-{case_id}-d{history.last_draw_no}-{history.source_sha256[:12]}"),
        "operation": "predict",
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": MODEL_REVISION,
        "source_revision": SOURCE_REVISION,
        "model_license": MODEL_LICENSE,
        "game_geometry": {
            "game_id": geometry.game_id,
            "position_count": geometry.position_count,
            "candidate_min": geometry.candidate_min,
            "candidate_max": geometry.candidate_max,
            "strictly_increasing": geometry.strictly_increasing,
        },
        "series_layout": "position_multivariate",
        "position_columns": list(history.position_columns),
        "history": [dict(row.values) for row in selected],
        "timestamps": [row.draw_no for row in selected],
        "time_semantics": "draw_sequence",
        "context_length": context,
        "prediction_length": horizon,
        "native_quantile_levels": [index / 10 for index in range(1, 10)],
        "point_method": "median_q0.5",
        "batch_size": 1,
        "decode_block_size": 32,
        "device": device,
        "dtype": "float32",
        "seed": 1,
        "local_files_only": True,
        "snapshot_path": str(snapshot_path.resolve()),
    }


def write_request_set(
    histories: dict[str, HistoryExport],
    *,
    output_root: Path,
    snapshot_path: Path,
) -> dict[str, Any]:
    if set(histories) != set(FORMAL_GAMES):
        raise ValueError(f"histories must exactly cover {list(FORMAL_GAMES)}")
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"request output directory is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for game in FORMAL_GAMES:
        history = histories[game]
        for context in FORMAL_CONTEXTS:
            for horizon in FORMAL_HORIZONS:
                for device in FORMAL_DEVICES:
                    request = build_request(
                        history,
                        context=context,
                        horizon=horizon,
                        device=device,
                        snapshot_path=snapshot_path,
                    )
                    filename = f"{game}-c{context}-h{horizon}-{device}.json"
                    output_path = output_root / filename
                    output_path.write_text(
                        json.dumps(request, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    entries.append(
                        {
                            "case_id": filename.removesuffix(".json"),
                            "path": filename,
                            "sha256": sha256_file(output_path),
                            "source_sha256": history.source_sha256,
                            "cutoff_draw_no": history.last_draw_no,
                        }
                    )
    if len(entries) != 90:
        raise RuntimeError(f"request set must contain 90 cases, got {len(entries)}")
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "cutoff_policy": "same_last_observed_draw_per_game",
        "future_actuals_used": False,
        "snapshot_path": str(snapshot_path.resolve()),
        "source_exports": {
            game: {
                "path": str(histories[game].source_path.resolve()),
                "sha256": histories[game].source_sha256,
                "row_count": len(histories[game].rows),
                "last_draw_no": histories[game].last_draw_no,
            }
            for game in FORMAL_GAMES
        },
        "request_count": len(entries),
        "requests": entries,
    }
    manifest_path = output_root / "REQUEST_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
