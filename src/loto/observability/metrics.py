from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge, Histogram

    STAGE_TOTAL = Counter("loto_stage_total", "Stage transitions", ["stage", "status"])
    STAGE_DURATION = Histogram("loto_stage_duration_seconds", "Stage duration", ["stage"])
    FORECAST_SEALED = Counter("loto_forecast_sealed_total", "Sealed forecasts")
    GPU_EVIDENCE_OK = Gauge("loto_gpu_evidence_ok", "Whether GPU evidence gate passed")
    RESEARCH_TRIAL_TOTAL = Counter(
        "loto_research_trial_total", "Research trials", ["model_id", "status"]
    )
    RESEARCH_TRIAL_DURATION = Histogram(
        "loto_research_trial_duration_seconds", "Research trial duration", ["model_id"]
    )
    RESEARCH_METRIC = Gauge(
        "loto_research_metric", "Latest research metric", ["model_id", "metric"]
    )
    DATA_GAME_TOTAL = Counter("loto_data_game_total", "Data pipeline games", ["game", "status"])
    NOTIFICATION_TOTAL = Counter(
        "loto_notification_total", "Notification attempts", ["channel", "status"]
    )
except Exception:  # pragma: no cover
    STAGE_TOTAL = STAGE_DURATION = FORECAST_SEALED = GPU_EVIDENCE_OK = None
    RESEARCH_TRIAL_TOTAL = RESEARCH_TRIAL_DURATION = RESEARCH_METRIC = None
    DATA_GAME_TOTAL = NOTIFICATION_TOTAL = None


def observe_trial(
    model_id: str, status: str, duration: float, metrics: dict[str, float] | None = None
) -> None:
    if RESEARCH_TRIAL_TOTAL is None:
        return
    RESEARCH_TRIAL_TOTAL.labels(model_id=model_id, status=status).inc()
    RESEARCH_TRIAL_DURATION.labels(model_id=model_id).observe(max(0.0, duration))
    for key, value in (metrics or {}).items():
        try:
            RESEARCH_METRIC.labels(model_id=model_id, metric=key).set(float(value))
        except (TypeError, ValueError):
            continue
