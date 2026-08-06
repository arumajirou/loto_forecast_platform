from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from loto.probabilistic.kdpp_certification_gate import sha256_file, validate_sha256
from loto.probabilistic.kdpp_history_contracts import (
    RAW_SOURCE_FILES,
    _GAME_SPECS,
    RawHistoryApproval,
    RawHistoryHandoff,
    RawHistoryVerification,
)


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path.name}")
    return payload


def _parse_utc_text(value: str, label: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be UTC")
    return parsed


def _regular_top_level_files(root: Path) -> dict[str, Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("source handoff root is missing or unsafe")
    result: dict[str, Path] = {}
    for path in root.iterdir():
        if path.is_symlink() or path.is_dir():
            raise ValueError("source handoff forbids symlinks and subdirectories")
        if path.is_file():
            result[path.name] = path
    return result


def validate_materialized_raw_history(
    root: Path,
) -> tuple[RawHistoryHandoff, RawHistoryApproval, RawHistoryVerification]:
    files = _regular_top_level_files(root)
    if set(files) != RAW_SOURCE_FILES:
        raise ValueError("source handoff file set mismatch")
    handoff = RawHistoryHandoff.model_validate(_load_object(files["HISTORY_HANDOFF.json"]))
    approval = RawHistoryApproval.model_validate(_load_object(files["history_approval.json"]))
    verification = RawHistoryVerification.model_validate(
        _load_object(files["history_verification.json"])
    )
    _parse_utc_text(handoff.materialized_at, "materialized_at")
    _parse_utc_text(handoff.reviewed_at, "handoff reviewed_at")
    _parse_utc_text(approval.reviewed_at, "approval reviewed_at")
    if handoff.approval_sha256 != sha256_file(files["history_approval.json"]):
        raise ValueError("handoff approval hash mismatch")
    if handoff.verification_sha256 != sha256_file(files["history_verification.json"]):
        raise ValueError("handoff verification hash mismatch")
    if handoff.export_manifest_sha256 != approval.binding.export_manifest_sha256:
        raise ValueError("handoff export manifest hash mismatch")
    if handoff.source_export_root != approval.binding.export_root:
        raise ValueError("handoff source export identity mismatch")
    if handoff.reviewer != approval.reviewer or handoff.reviewed_at != approval.reviewed_at:
        raise ValueError("handoff reviewer identity mismatch")
    if approval.binding.verification_sha256 != sha256_file(files["history_verification.json"]):
        raise ValueError("approval verification hash mismatch")
    if verification.export_root != approval.binding.export_root:
        raise ValueError("verification export root mismatch")
    for name, digest in handoff.copied_files.items():
        if sha256_file(files[name]) != digest:
            raise ValueError(f"source handoff SHA-256 mismatch: {name}")
    verified_games = {game.game_id: game for game in verification.games}
    for game, binding in approval.binding.games.items():
        if binding.json_path != f"{game}.json":
            raise ValueError("approval JSON path mismatch")
        if binding.json_sha256 != sha256_file(files[f"{game}.json"]):
            raise ValueError("approval JSON hash mismatch")
        verified = verified_games[game]
        if verified.draw_count != binding.draw_count:
            raise ValueError("verification draw count mismatch")
        if verified.json_sha256 != binding.json_sha256:
            raise ValueError("verification JSON hash mismatch")
        if verified.parquet_sha256 != binding.parquet_sha256:
            raise ValueError("verification Parquet hash mismatch")
    return handoff, approval, verification


def _strict_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def parse_game_history(
    path: Path,
    *,
    game: str,
) -> tuple[np.ndarray, tuple[str, ...], np.ndarray]:
    if game not in _GAME_SPECS:
        raise ValueError("unsupported game")
    payload = _load_object(path)
    if set(payload) != {"schema_version", "game_id", "position_columns", "rows"}:
        raise ValueError("history JSON field set mismatch")
    if payload["schema_version"] != 1 or payload["game_id"] != game:
        raise ValueError("history JSON identity mismatch")
    position_count, minimum, maximum, increasing = _GAME_SPECS[game]
    expected_columns = [f"N{index}" for index in range(1, position_count + 1)]
    if payload["position_columns"] != expected_columns:
        raise ValueError("history position columns mismatch")
    rows = payload["rows"]
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("history rows must be a non-empty list")
    values: list[list[int]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != {"draw_no", "values"}:
            raise ValueError("history row field set mismatch")
        if _strict_int(row["draw_no"], "draw_no") != index:
            raise ValueError("draw_no must be one-based and gap-free")
        row_values = row["values"]
        if not isinstance(row_values, dict) or list(row_values) != expected_columns:
            raise ValueError("history values do not match position columns")
        parsed = [_strict_int(row_values[column], column) for column in expected_columns]
        if any(value < minimum or value > maximum for value in parsed):
            raise ValueError("history value outside game domain")
        if increasing and any(right <= left for left, right in zip(parsed, parsed[1:])):
            raise ValueError("lottery positions must be strictly increasing")
        values.append(parsed)
    return (
        np.asarray(values, dtype=np.int64),
        tuple(expected_columns),
        np.arange(1, len(values) + 1, dtype=np.int64),
    )


def build_indicator_matrix(
    values: np.ndarray,
    *,
    game: str,
    position: int | None,
) -> tuple[np.ndarray, tuple[str, ...], int, str]:
    position_count, _, maximum, _ = _GAME_SPECS[game]
    if values.shape[1] != position_count:
        raise ValueError("history value shape mismatch")
    if game in {"numbers3", "numbers4"}:
        if position is None or position < 1 or position > position_count:
            raise ValueError("Numbers3/4 require a valid position")
        item_ids = tuple(f"n{position}:{digit}" for digit in range(10))
        indicators = np.zeros((values.shape[0], 10), dtype=np.uint8)
        indicators[np.arange(values.shape[0]), values[:, position - 1]] = 1
        return indicators, item_ids, 1, "position_local"
    if position is not None:
        raise ValueError("unordered games do not accept position")
    item_ids = tuple(str(index) for index in range(1, maximum + 1))
    indicators = np.zeros((values.shape[0], maximum), dtype=np.uint8)
    for row_index, row in enumerate(values):
        indicators[row_index, row - 1] = 1
    return indicators, item_ids, position_count, "unordered_fixed_cardinality"
