import pandas as pd

from loto.orchestration.pipeline import run_trusted_vertical_slice
from loto.registry.release import verify_release_bundle


def test_trusted_vertical_slice_produces_sealed_forecast(tmp_path):
    rows = []
    for draw_no in range(1, 31):
        nums = sorted((((draw_no * 3 + j * 5) % 37) + 1 for j in range(7)))
        if len(set(nums)) < 7:
            nums = list(range(1, 8))
        rows.append({"draw_no": draw_no, "draw_date": (pd.Timestamp("2026-01-01") + pd.Timedelta(days=7 * (draw_no - 1))).date().isoformat(), **{f"n{i+1}": n for i, n in enumerate(nums)}})
    input_csv = tmp_path / "draws.csv"
    pd.DataFrame(rows).to_csv(input_csv, index=False)
    result = run_trusted_vertical_slice(input_csv, tmp_path / "out", secret=b"test-secret", backtest_draws=5)
    assert result["seal_verified"] is True
    assert len(result["forecast"]["combination"]["numbers"]) == 7
    assert (tmp_path / "out" / "events.jsonl").exists()
    assert (tmp_path / "out" / "resource_evidence.json").exists()
    assert (tmp_path / "out" / "release_bundle.json").exists()
    assert (tmp_path / "out" / "mlflow_status.json").exists()
    assert verify_release_bundle(tmp_path / "out" / "release_bundle.json") is True
