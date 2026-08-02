"""Tests for MTP metrics aggregation and calculation."""

import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the metrics aggregation functions from mtp_comparison
# We need to import the module to access the aggregation logic
try:
    from benchmarks.mtp_comparison import MetricResult, aggregate_metrics

    HAS_METRICS = True
except ImportError:
    HAS_METRICS = False


class TestMetricsAggregation:
    """Test metrics aggregation logic."""

    def setup_method(self):
        """Setup test data."""
        if not HAS_METRICS:
            pytest.skip("mtp_comparison module not available")

    def test_aggregate_single_config(self):
        """Test aggregation with single configuration."""
        results = [
            MetricResult(
                elapsed_seconds=1.5,
                generated_tokens=100,
                tokens_per_sec=66.67,
                json_corrupted=False,
                factual_accuracy=0.8,
                mtp_config="A_no_mtp",
            ),
            MetricResult(
                elapsed_seconds=1.8,
                generated_tokens=120,
                tokens_per_sec=66.67,
                json_corrupted=False,
                factual_accuracy=0.9,
                mtp_config="A_no_mtp",
            ),
        ]

        aggregated = aggregate_metrics(results)

        assert "A_no_mtp" in aggregated
        data = aggregated["A_no_mtp"]
        assert data["count"] == 2
        assert abs(data["avg_elapsed"] - 1.65) < 0.01
        assert abs(data["avg_tps"] - 66.67) < 0.01
        assert data["json_corruption_rate"] == 0.0
        assert abs(data["avg_accuracy"] - 0.85) < 0.01

    def test_aggregate_multiple_configs(self):
        """Test aggregation across multiple configurations."""
        results = [
            MetricResult(
                elapsed_seconds=1.5,
                generated_tokens=100,
                tokens_per_sec=66.67,
                json_corrupted=False,
                factual_accuracy=0.8,
                mtp_config="A_no_mtp",
            ),
            MetricResult(
                elapsed_seconds=1.2,
                generated_tokens=150,
                tokens_per_sec=125.0,
                json_corrupted=True,
                factual_accuracy=0.7,
                mtp_config="B_conservative",
            ),
            MetricResult(
                elapsed_seconds=1.0,
                generated_tokens=200,
                tokens_per_sec=200.0,
                json_corrupted=True,
                factual_accuracy=0.6,
                mtp_config="C_default",
            ),
        ]

        aggregated = aggregate_metrics(results)

        assert "A_no_mtp" in aggregated
        assert "B_conservative" in aggregated
        assert "C_default" in aggregated

        # B_conservative has 1 corrupted out of 1 = 100%
        assert aggregated["B_conservative"]["json_corruption_rate"] == 1.0

        # C_default has 1 corrupted out of 1 = 100%
        assert aggregated["C_default"]["json_corruption_rate"] == 1.0

    def test_aggregate_empty_results(self):
        """Test aggregation with empty results."""
        aggregated = aggregate_metrics([])
        assert len(aggregated) == 0

    def test_aggregate_single_result(self):
        """Test aggregation with single result."""
        results = [
            MetricResult(
                elapsed_seconds=2.0,
                generated_tokens=200,
                tokens_per_sec=100.0,
                json_corrupted=False,
                factual_accuracy=0.9,
                mtp_config="A_no_mtp",
            ),
        ]

        aggregated = aggregate_metrics(results)

        assert "A_no_mtp" in aggregated
        data = aggregated["A_no_mtp"]
        assert data["count"] == 1
        assert abs(data["avg_elapsed"] - 2.0) < 0.01
        assert abs(data["avg_tps"] - 100.0) < 0.01
        assert data["json_corruption_rate"] == 0.0
        assert abs(data["avg_accuracy"] - 0.9) < 0.01
