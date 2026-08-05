from __future__ import annotations

import hashlib
import json
import math
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict

from .contracts import GameGeometry


class TimelineMappingRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_index: int
    source_order: Any
    source_timestamp: str
    synthetic_timestamp: str


class CompiledHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[dict[str, Any], ...]
    timeline_mapping: tuple[TimelineMappingRow, ...]
    source_order_sha256: str
    mapping_sha256: str
    geometry_sha256: str


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compile_regular_history(
    history: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    geometry: GameGeometry,
) -> CompiledHistory:
    if not history:
        raise ValueError("history must not be empty")

    timeline = geometry.timeline
    source_orders: list[Any] = []
    source_mapping_payload: list[dict[str, Any]] = []
    mapping_rows: list[TimelineMappingRow] = []
    records: list[dict[str, Any]] = []

    for source_index, row in enumerate(history):
        missing = [column for column in geometry.position_columns if column not in row]
        if missing:
            raise ValueError(f"history row {source_index} is missing position columns: {missing}")
        if timeline.source_order_field not in row:
            raise ValueError(
                f"history row {source_index} is missing source order field "
                f"{timeline.source_order_field!r}"
            )
        if timeline.source_timestamp_field not in row:
            raise ValueError(
                f"history row {source_index} is missing source timestamp field "
                f"{timeline.source_timestamp_field!r}"
            )

        source_order = row[timeline.source_order_field]
        source_timestamp = str(row[timeline.source_timestamp_field])
        source_orders.append(source_order)
        synthetic_timestamp = timeline.base_timestamp + timedelta(days=source_index)
        mapping_row = TimelineMappingRow(
            source_index=source_index,
            source_order=source_order,
            source_timestamp=source_timestamp,
            synthetic_timestamp=synthetic_timestamp.isoformat(),
        )
        mapping_rows.append(mapping_row)
        source_mapping_payload.append(
            {
                "source_index": source_index,
                "source_order": source_order,
                "source_timestamp": source_timestamp,
            }
        )

        values: list[float] = []
        for column in geometry.position_columns:
            try:
                value = float(row[column])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"history row {source_index} column {column!r} is not numeric"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"history row {source_index} column {column!r} is not finite"
                )
            if value < geometry.candidate_min or value > geometry.candidate_max:
                raise ValueError(
                    f"history row {source_index} column {column!r}={value} is outside "
                    f"[{geometry.candidate_min}, {geometry.candidate_max}]"
                )
            values.append(value)

        if not geometry.allow_duplicates and len(set(values)) != len(values):
            raise ValueError(f"history row {source_index} contains duplicate position values")
        if geometry.sort_policy == "ascending" and values != sorted(values):
            raise ValueError(f"history row {source_index} position values are not ascending")

        for position_index, (column, value) in enumerate(
            zip(geometry.position_columns, values, strict=True),
            start=1,
        ):
            records.append(
                {
                    "item_id": f"position-{position_index}",
                    "timestamp": synthetic_timestamp.isoformat(),
                    "target": value,
                    "source_column": column,
                    "source_index": source_index,
                }
            )

    if len({_canonical_sha256(value) for value in source_orders}) != len(source_orders):
        raise ValueError("source order values must be unique")

    mapping_payload = [row.model_dump(mode="json") for row in mapping_rows]
    return CompiledHistory(
        records=tuple(records),
        timeline_mapping=tuple(mapping_rows),
        source_order_sha256=_canonical_sha256(source_mapping_payload),
        mapping_sha256=_canonical_sha256(mapping_payload),
        geometry_sha256=_canonical_sha256(geometry.model_dump(mode="json")),
    )
