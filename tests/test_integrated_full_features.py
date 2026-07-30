from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from loto.api.app import create_app
from loto.data.integrated import acquire_and_build_many
from loto.data.lotteries import select_lottery_specs
from loto.models.catalog import get_model_spec
from loto.models.workers import position_values_to_candidate_probabilities
from loto.notifications import NotificationConfig, NotificationSender, build_run_summary
from loto.scheduling import SchedulePolicy, build_schedule_plan


def _write_source(path: Path, columns: dict[str, list]) -> None:
    pd.DataFrame(columns).to_csv(path, index=False, encoding="utf-8-sig")


def test_catalog_contains_all_neuralforecast_auto_families():
    assert get_model_spec("nf-auto-nhits").class_name == "AutoNHITS"
    assert get_model_spec("nf-auto-tft").class_name == "AutoTFT"
    assert get_model_spec("nf-auto-rmok").library == "neuralforecast_auto"


def test_position_probabilities_are_model_derived_and_valid():
    history = pd.DataFrame({f"n{i}": np.arange(i, i + 40) % (38 - i) + i for i in range(1, 8)})
    values = np.array([3, 8, 13, 19, 25, 31, 36], dtype=float)
    probabilities = position_values_to_candidate_probabilities(history, values)
    assert probabilities.shape == (37,)
    assert np.all((probabilities > 0) & (probabilities < 1))
    assert abs(float(probabilities.sum()) - 7.0) < 1e-5
    assert float(probabilities.std()) > 0.01


def test_all_game_local_acquisition_and_lineage(tmp_path):
    dates = ["2026-01-01", "2026-01-08", "2026-01-15"]
    sources: dict[str, str] = {}
    specs = {spec.key: spec for spec in select_lottery_specs("all")}
    for game, spec in specs.items():
        path = tmp_path / f"{game}.csv"
        if spec.kind == "numbers":
            _write_source(path, {"回号": [1, 2, 3], "抽選日": dates, "抽選数字": ["012", "345", "678"] if spec.digits_count == 3 else ["0123", "3456", "6789"]})
        else:
            data: dict[str, list] = {"回号": [1, 2, 3], "抽選日": dates}
            for i in range(1, (spec.main_count or 0) + 1):
                data[f"本数字{i}"] = [i, i + 1, i + 2]
            for i in range(1, spec.bonus_count + 1):
                data[f"ボーナス数字{i}"] = [spec.main_count + i + j for j in range(3)]
            _write_source(path, data)
        sources[game] = str(path)
    result = acquire_and_build_many(games="all", output_dir=tmp_path / "out", source_files=sources, continue_on_error=False)
    assert result["status"] == "SUCCEEDED"
    assert set(result["successful_games"]) == set(specs)
    for game in specs:
        report = json.loads((tmp_path / "out" / game / "acquisition_report.json").read_text(encoding="utf-8"))
        assert report["quality"]["status"] == "PASS"
        assert report["stages"][-1]["status"] == "SUCCEEDED"
        assert Path(report["bundle"]["manifest"]).exists()


def test_notification_safe_default_writes_only_local_file(tmp_path):
    config = NotificationConfig(enabled=False, file_enabled=True, file_path="notify/events.jsonl")
    sender = NotificationSender(config, base_dir=tmp_path)
    summary = build_run_summary({"run_id": "r1", "status": "SUCCEEDED"}, output_dir=tmp_path)
    results = sender.send_all(summary)
    assert results[0].status == "SENT"
    assert results[1].status == "SKIPPED"
    assert (tmp_path / "notify/events.jsonl").exists()


def test_schedule_plan_is_draw_aware():
    now = datetime(2026, 7, 30, 14, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    plan = build_schedule_plan("loto7,numbers3", now=now, policy=SchedulePolicy(run_hour=20, run_minute=30))
    runs = {row["game"]: row for row in plan["runs"]}
    assert runs["loto7"]["run_at"].startswith("2026-07-31T20:30")
    assert runs["numbers3"]["run_at"].startswith("2026-07-30T20:30")


def test_api_exposes_runs_events_resources_and_games(tmp_path, monkeypatch):
    monkeypatch.setenv("LOTO_AUTH_DISABLED", "1")
    run_dir = tmp_path / "runs" / "demo"
    run_dir.mkdir(parents=True)
    (run_dir / "research_summary.json").write_text(json.dumps({"run_id": "demo-run", "status": "SUCCEEDED"}))
    (run_dir / "events.jsonl").write_text(json.dumps({"event": "x"}) + "\n")
    (run_dir / "resource_samples.jsonl").write_text(json.dumps({"process": {"pid": 1}}) + "\n")
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v2/data/games").status_code == 200
    plan = client.post("/api/v2/model-plan", json={"model_name": "AutoNHITS", "h": 1, "backend": "optuna", "num_samples": 10})
    assert plan.status_code == 200
    assert plan.json()["search_algorithm"].startswith("TPE")
    assert client.get("/api/v2/runs").json()[0]["run_id"] == "demo-run"
    assert client.get("/api/v2/runs/demo-run/events").json()[0]["event"] == "x"
    assert client.get("/api/v2/runs/demo-run/resources").json()[0]["process"]["pid"] == 1
