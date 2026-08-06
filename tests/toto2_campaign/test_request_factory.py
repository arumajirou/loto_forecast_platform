from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.toto2_campaign.request_factory import (
    FORMAL_GAMES,
    build_request,
    load_history_export,
    write_request_set,
)


def _history_payload(game: str, count: int, max_value: int) -> dict[str, object]:
    columns = [f"n{index}" for index in range(1, count + 1)]
    rows = []
    for draw_no in range(1, 521):
        if game in {"numbers3", "numbers4"}:
            values = {
                column: float((draw_no + index) % 10)
                for index, column in enumerate(columns)
            }
        else:
            start = 1 + draw_no % (max_value - count)
            values = {
                column: float(start + index)
                for index, column in enumerate(columns)
            }
        rows.append({"draw_no": draw_no, "values": values})
    return {
        "schema_version": 1,
        "game_id": game,
        "position_columns": columns,
        "rows": rows,
    }


def _write_histories(root: Path) -> dict[str, object]:
    specs = {
        "numbers3": (3, 9),
        "numbers4": (4, 9),
        "miniloto": (5, 31),
        "loto6": (6, 43),
        "loto7": (7, 37),
    }
    histories = {}
    for game, (count, maximum) in specs.items():
        path = root / f"{game}.json"
        path.write_text(
            json.dumps(_history_payload(game, count, maximum)),
            encoding="utf-8",
        )
        histories[game] = load_history_export(path)
    return histories


def test_write_request_set_creates_exact_formal_matrix(tmp_path: Path) -> None:
    history_root = tmp_path / "history"
    history_root.mkdir()
    histories = _write_histories(history_root)
    requests_root = tmp_path / "requests"
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    manifest = write_request_set(
        histories,
        output_root=requests_root,
        snapshot_path=snapshot,
    )

    assert manifest["request_count"] == 90
    assert set(manifest["source_exports"]) == set(FORMAL_GAMES)
    assert len(list(requests_root.glob("*.json"))) == 91
    request = json.loads(
        (requests_root / "loto7-c128-h5-cuda.json").read_text(encoding="utf-8")
    )
    assert request["context_length"] == 128
    assert request["prediction_length"] == 5
    assert request["device"] == "cuda"
    assert len(request["history"]) == 128
    assert request["timestamps"][-1] == 520
    assert request["local_files_only"] is True


def test_contexts_share_the_same_cutoff(tmp_path: Path) -> None:
    path = tmp_path / "numbers3.json"
    path.write_text(
        json.dumps(_history_payload("numbers3", 3, 9)),
        encoding="utf-8",
    )
    history = load_history_export(path)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    request_128 = build_request(
        history,
        context=128,
        horizon=1,
        device="cpu",
        snapshot_path=snapshot,
    )
    request_512 = build_request(
        history,
        context=512,
        horizon=1,
        device="cpu",
        snapshot_path=snapshot,
    )

    assert request_128["timestamps"][-1] == request_512["timestamps"][-1]
    assert request_128["history"] == request_512["history"][-128:]


def test_history_rejects_draw_gap(tmp_path: Path) -> None:
    payload = _history_payload("numbers3", 3, 9)
    payload["rows"][300]["draw_no"] = 999
    path = tmp_path / "numbers3.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="gap-free"):
        load_history_export(path)


def test_history_rejects_non_increasing_loto_row(tmp_path: Path) -> None:
    payload = _history_payload("loto7", 7, 37)
    payload["rows"][0]["values"]["n2"] = payload["rows"][0]["values"]["n1"]
    path = tmp_path / "loto7.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="strictly increasing"):
        load_history_export(path)
