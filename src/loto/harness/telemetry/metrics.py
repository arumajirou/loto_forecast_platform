from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Gauge, Histogram


class HarnessMetrics:
    def __init__(self, registry=REGISTRY) -> None:
        self.requests = Counter(
            "loto_harness_requests_total",
            "Harness inference requests",
            ["engine", "model", "status"],
            registry=registry,
        )
        self.request_duration = Histogram(
            "loto_harness_request_duration_seconds",
            "End-to-end inference duration",
            ["engine", "model"],
            registry=registry,
        )
        self.prompt_tokens = Counter(
            "loto_harness_prompt_tokens_total",
            "Prompt tokens",
            ["engine", "model"],
            registry=registry,
        )
        self.completion_tokens = Counter(
            "loto_harness_completion_tokens_total",
            "Completion tokens",
            ["engine", "model"],
            registry=registry,
        )
        self.cached_tokens = Counter(
            "loto_harness_cached_tokens_total",
            "Cached prompt tokens",
            ["engine", "model"],
            registry=registry,
        )
        self.context_tokens = Gauge(
            "loto_harness_context_tokens",
            "Most recently compiled context token count",
            registry=registry,
        )
        self.compression_ratio = Gauge(
            "loto_harness_compression_ratio",
            "Most recent final/raw context token ratio",
            registry=registry,
        )
        self.profile_requests = Counter(
            "loto_harness_profile_requests_total",
            "Requests after model-profile application",
            ["model", "profile", "mode", "task", "status"],
            registry=registry,
        )
        self.profile_duration = Histogram(
            "loto_harness_profile_request_duration_seconds",
            "End-to-end duration by model profile",
            ["model", "profile", "mode", "task"],
            registry=registry,
        )
        self.loop_iterations = Histogram(
            "loto_harness_loop_iterations",
            "Engineering loop iterations",
            ["status"],
            buckets=(1, 2, 3, 4, 5, 8, 13, 21),
            registry=registry,
        )

    def record_chat(self, engine: str, model: str, response, seconds: float) -> None:
        self.requests.labels(engine, model, "success").inc()
        self.request_duration.labels(engine, model).observe(seconds)
        self.prompt_tokens.labels(engine, model).inc(response.usage.prompt_tokens)
        self.completion_tokens.labels(engine, model).inc(response.usage.completion_tokens)
        self.cached_tokens.labels(engine, model).inc(response.usage.cached_tokens)


    def record_profile(
        self,
        model: str,
        profile: str,
        mode: str,
        task: str,
        status: str,
        seconds: float,
    ) -> None:
        self.profile_requests.labels(model, profile, mode, task, status).inc()
        self.profile_duration.labels(model, profile, mode, task).observe(seconds)
