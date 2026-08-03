from loto.probabilistic.progress import ProgressEstimator, progress_bar, render_dashboard


def test_eta_uses_resource_limits() -> None:
    estimator = ProgressEstimator(
        outer_workers=8,
        limits={"gpu": 1, "heavy_cpu": 2, "light_cpu": 8},
        defaults={"gpu": 100, "heavy_cpu": 200, "light_cpu": 10},
    )
    eta = estimator.estimate(
        {"gpu": 2, "heavy_cpu": 4, "light_cpu": 8},
        {},
    )
    assert eta["estimated_remaining_seconds"] >= 400
    assert eta["eta_confidence"] == "low"


def test_dashboard_has_bar_and_eta() -> None:
    payload = {
        "status": "RUNNING",
        "timestamp": "2026-08-03T15:00:00+09:00",
        "completed_allowed": 16,
        "trials_allowed": 64,
        "progress_percent": 25.0,
        "status_counts": {"PASS": 14},
        "elapsed_seconds": 120,
        "eta": {
            "estimated_remaining_text": "10分0秒",
            "estimated_completion_at": "2026-08-03T15:12:00+09:00",
            "eta_confidence": "medium",
        },
        "parallelism": {
            "running_total": 4,
            "outer_workers": 8,
            "peak_running_total": 8,
            "running_by_resource": {"gpu": 1, "heavy_cpu": 2, "light_cpu": 1},
        },
        "running_trials": ["a", "b"],
        "gpu": {"available": False},
        "run_dir": "/tmp/run",
    }
    text = render_dashboard(payload)
    assert "25.00%" in text
    assert "終了予測" in text
    assert "現在=4/8" in text
    assert progress_bar(50, 10).count("█") == 5
