from __future__ import annotations

import json

import pandas as pd

from loto.data.lineage import atomic_write_frame_csv, atomic_write_json


def test_atomic_csv_and_json_are_utf8_and_readable(tmp_path):
    csv_path = atomic_write_frame_csv(pd.DataFrame({"名称": ["ミニロト"]}), tmp_path / "data.csv")
    json_path = atomic_write_json(tmp_path / "report.json", {"名称": "ミニロト"})

    assert "ミニロト" in csv_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["名称"] == "ミニロト"
