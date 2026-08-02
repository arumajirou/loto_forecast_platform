"""Unit tests for validation metrics aggregation and Pareto optimality.

Tests the logic that selects the best configuration from multiple runs,
using success rate, token efficiency, speed, and robustness as criteria.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class ValidationMetric:
    """Represents a single configuration's performance metrics."""

    config_label: str
    success_rate: float
    avg_input_tokens: int
    avg_output_tokens: int
    avg_elapsed: float
    avg_retry_count: float

    @property
    def total_tokens(self) -> int:
        return self.avg_input_tokens + self.avg_output_tokens

    @property
    def token_efficiency(self) -> float:
        """Tokens per success — lower is better."""
        if self.success_rate == 0:
            return float("inf")
        return self.total_tokens / self.success_rate


def select_best_config(metrics: list[ValidationMetric]) -> ValidationMetric | None:
    """Select the Pareto-optimal configuration.

    Criteria:
    1. Highest success rate
    2. Among those, lowest token consumption
    3. Among those, lowest elapsed time

    Returns the best config or None if input is empty.
    """
    if not metrics:
        return None

    # Sort by success_rate descending, then total_tokens ascending, then elapsed ascending
    sorted_metrics = sorted(metrics, key=lambda m: (-m.success_rate, m.total_tokens, m.avg_elapsed))

    return sorted_metrics[0]


def compute_pareto_frontier(metrics: list[ValidationMetric]) -> list[ValidationMetric]:
    """Compute the Pareto frontier of configurations.

    A configuration is on the Pareto frontier if no other configuration
    dominates it in ALL criteria (higher success, lower tokens, lower time).
    """
    if not metrics:
        return []

    frontier = []
    for i, m1 in enumerate(metrics):
        dominated = False
        for j, m2 in enumerate(metrics):
            if i == j:
                continue
            # m2 dominates m1 if m2 is better in ALL criteria
            if (
                m2.success_rate >= m1.success_rate
                and m2.total_tokens <= m1.total_tokens
                and m2.avg_elapsed <= m1.avg_elapsed
                and (
                    m2.success_rate > m1.success_rate
                    or m2.total_tokens < m1.total_tokens
                    or m2.avg_elapsed < m1.avg_elapsed
                )
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(m1)

    return frontier


class TestSelectBestConfig:
    """Test the best configuration selection logic."""

    def test_select_best_single_metric(self):
        """Test selection with single metric."""
        metrics = [
            ValidationMetric(
                config_label="Config1",
                success_rate=0.95,
                avg_input_tokens=200,
                avg_output_tokens=300,
                avg_elapsed=1.5,
                avg_retry_count=1.0,
            )
        ]
        best = select_best_config(metrics)
        assert best is not None
        assert best.config_label == "Config1"
        assert best.success_rate == 0.95

    def test_select_best_multiple_metrics(self):
        """Test selection among multiple configurations."""
        metrics = [
            ValidationMetric(
                config_label="Config_A",
                success_rate=0.85,
                avg_input_tokens=150,
                avg_output_tokens=200,
                avg_elapsed=1.2,
                avg_retry_count=0.5,
            ),
            ValidationMetric(
                config_label="Config_B",
                success_rate=0.92,
                avg_input_tokens=250,
                avg_output_tokens=350,
                avg_elapsed=2.0,
                avg_retry_count=1.5,
            ),
            ValidationMetric(
                config_label="Config_C",
                success_rate=0.94,
                avg_input_tokens=220,
                avg_output_tokens=320,
                avg_elapsed=1.8,
                avg_retry_count=2.0,
            ),
        ]
        best = select_best_config(metrics)
        assert best is not None
        # Config_C has highest success rate (0.94)
        assert best.config_label == "Config_C"
        assert best.success_rate == 0.94

    def test_select_best_tiebreaker_tokens(self):
        """Test tiebreaker when success rates are equal."""
        metrics = [
            ValidationMetric(
                config_label="Config_X",
                success_rate=0.90,
                avg_input_tokens=300,
                avg_output_tokens=400,
                avg_elapsed=2.5,
                avg_retry_count=2.0,
            ),
            ValidationMetric(
                config_label="Config_Y",
                success_rate=0.90,
                avg_input_tokens=200,
                avg_output_tokens=250,
                avg_elapsed=1.5,
                avg_retry_count=1.0,
            ),
        ]
        best = select_best_config(metrics)
        assert best is not None
        # Both have 0.90 success, Config_Y has fewer tokens
        assert best.config_label == "Config_Y"
        assert best.total_tokens == 450

    def test_select_best_empty_input(self):
        """Test selection with empty input."""
        best = select_best_config([])
        assert best is None

    def test_select_best_low_success(self):
        """Test selection when all configs have low success."""
        metrics = [
            ValidationMetric(
                config_label="Config_Low",
                success_rate=0.50,
                avg_input_tokens=100,
                avg_output_tokens=150,
                avg_elapsed=0.8,
                avg_retry_count=3.0,
            ),
        ]
        best = select_best_config(metrics)
        assert best is not None
        assert best.config_label == "Config_Low"
        assert best.success_rate == 0.50


class TestTokenEfficiency:
    """Test token efficiency calculation."""

    def test_token_efficiency_normal(self):
        """Test normal token efficiency calculation."""
        metric = ValidationMetric(
            config_label="Test",
            success_rate=0.80,
            avg_input_tokens=200,
            avg_output_tokens=300,
            avg_elapsed=1.5,
            avg_retry_count=1.0,
        )
        assert metric.total_tokens == 500
        assert metric.token_efficiency == pytest.approx(625.0)

    def test_token_efficiency_zero_success(self):
        """Test token efficiency with zero success rate."""
        metric = ValidationMetric(
            config_label="Test",
            success_rate=0.0,
            avg_input_tokens=100,
            avg_output_tokens=150,
            avg_elapsed=1.0,
            avg_retry_count=5.0,
        )
        assert metric.token_efficiency == float("inf")

    def test_token_efficiency_high_success(self):
        """Test token efficiency with high success rate."""
        metric = ValidationMetric(
            config_label="Test",
            success_rate=0.95,
            avg_input_tokens=180,
            avg_output_tokens=270,
            avg_elapsed=1.2,
            avg_retry_count=0.5,
        )
        assert metric.total_tokens == 450
        assert metric.token_efficiency == pytest.approx(473.68, abs=0.01)


class TestParetoFrontier:
    """Test Pareto frontier computation."""

    def test_pareto_frontier_single(self):
        """Test Pareto frontier with single metric."""
        metrics = [
            ValidationMetric(
                config_label="Only",
                success_rate=0.90,
                avg_input_tokens=200,
                avg_output_tokens=300,
                avg_elapsed=1.5,
                avg_retry_count=1.0,
            )
        ]
        frontier = compute_pareto_frontier(metrics)
        assert len(frontier) == 1
        assert frontier[0].config_label == "Only"

    def test_pareto_frontier_multiple(self):
        """Test Pareto frontier with multiple metrics."""
        metrics = [
            ValidationMetric(
                config_label="A",
                success_rate=0.85,
                avg_input_tokens=150,
                avg_output_tokens=200,
                avg_elapsed=1.2,
                avg_retry_count=0.5,
            ),
            ValidationMetric(
                config_label="B",
                success_rate=0.92,
                avg_input_tokens=250,
                avg_output_tokens=350,
                avg_elapsed=2.0,
                avg_retry_count=1.5,
            ),
            ValidationMetric(
                config_label="C",
                success_rate=0.94,
                avg_input_tokens=220,
                avg_output_tokens=320,
                avg_elapsed=1.8,
                avg_retry_count=2.0,
            ),
        ]
        frontier = compute_pareto_frontier(metrics)
        # C dominates B (higher success, lower elapsed), so B is excluded
        # A and C are on the frontier (non-dominated)
        assert len(frontier) == 2
        labels = {m.config_label for m in frontier}
        assert "A" in labels
        assert "C" in labels
        assert "B" not in labels

    def test_pareto_frontier_empty(self):
        """Test Pareto frontier with empty input."""
        frontier = compute_pareto_frontier([])
        assert len(frontier) == 0

    def test_pareto_frontier_dominated(self):
        """Test that dominated configurations are excluded."""
        metrics = [
            # Dominant config
            ValidationMetric(
                config_label="Dominant",
                success_rate=0.95,
                avg_input_tokens=100,
                avg_output_tokens=150,
                avg_elapsed=0.8,
                avg_retry_count=0.5,
            ),
            # Dominated config
            ValidationMetric(
                config_label="Dominated",
                success_rate=0.80,
                avg_input_tokens=200,
                avg_output_tokens=300,
                avg_elapsed=2.0,
                avg_retry_count=2.0,
            ),
        ]
        frontier = compute_pareto_frontier(metrics)
        # Only Dominant should be on the frontier
        assert len(frontier) == 1
        assert frontier[0].config_label == "Dominant"
