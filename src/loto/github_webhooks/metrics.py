from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


@dataclass(frozen=True)
class WebhookMetrics:
    requests_total: Counter
    signature_failures_total: Counter
    duplicates_total: Counter
    ack_seconds: Histogram
    queue_depth: Gauge
    dead_letters_total: Counter


def create_metrics(registry: CollectorRegistry | None = None) -> WebhookMetrics:
    target = registry or CollectorRegistry()
    return WebhookMetrics(
        requests_total=Counter(
            "github_webhook_requests_total",
            "GitHub webhook receiver outcomes",
            ("event", "result"),
            registry=target,
        ),
        signature_failures_total=Counter(
            "github_webhook_signature_failures_total",
            "GitHub webhook signature failures",
            registry=target,
        ),
        duplicates_total=Counter(
            "github_webhook_duplicates_total",
            "GitHub webhook duplicate and conflict outcomes",
            ("result",),
            registry=target,
        ),
        ack_seconds=Histogram(
            "github_webhook_ack_seconds",
            "GitHub webhook acknowledgement duration",
            ("event", "result"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=target,
        ),
        queue_depth=Gauge(
            "github_webhook_queue_depth",
            "Durable GitHub webhook outbox depth",
            registry=target,
        ),
        dead_letters_total=Counter(
            "github_webhook_dead_letters_total",
            "GitHub webhook dead letters",
            ("handler",),
            registry=target,
        ),
    )
