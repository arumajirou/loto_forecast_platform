#!/usr/bin/env python3
"""
Unit tests for sealed evaluation metrics computation.

Tests the aggregation logic and relative improvement calculations
that are used in the sealed evaluation pipeline.
"""

from dataclasses import dataclass


@dataclass
class SealedMetric:
    """Metric result from sealed evaluation."""

    config_label: str
    success_rate: float
    avg_elapsed: float
    avg_input_tokens: int
    avg_output_tokens: int
    total_retries: int

    def to_dict(self):
        return {
            "config_label": self.config_label,
            "success_rate": self.success_rate,
            "avg_elapsed": self.avg_elapsed,
            "avg_input_tokens": self.avg_input_tokens,
            "avg_output_tokens": self.avg_output_tokens,
            "total_retries": self.total_retries,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            config_label=d["config_label"],
            success_rate=d["success_rate"],
            avg_elapsed=d["avg_elapsed"],
            avg_input_tokens=d["avg_input_tokens"],
            avg_output_tokens=d["avg_output_tokens"],
            total_retries=d["total_retries"],
        )


def compute_relative_improvement(base_rate: float, improved_rate: float) -> float:
    """Compute relative improvement percentage from base to improved rate.

    Formula: (improved - base) / base
    Returns float representing the improvement ratio.

    Edge cases:
    - base_rate == 0: returns inf if improved > 0, else 0.0
    """
    if base_rate == 0:
        return float("inf") if improved_rate > 0 else 0.0
    return (improved_rate - base_rate) / base_rate


def compute_token_efficiency_score(input_tokens: int, output_tokens: int, success: bool) -> float:
    """Compute a token efficiency score (higher is better).

    Formula: success * (input_tokens + output_tokens) / max_tokens
    Returns a score between 0.0 and 1.0.
    """
    total_tokens = input_tokens + output_tokens
    max_tokens = 10000  # Assume max 10K tokens per task
    if total_tokens == 0:
        return 0.0
    return success * total_tokens / max_tokens


def detect_overfitting(dev_success: float, sealed_success: float, threshold: float = 0.1) -> bool:
    """Detect potential overfitting between development and sealed sets.

    Args:
        dev_success: Success rate on development/validation set
        sealed_success: Success rate on sealed test set
        threshold: Maximum allowed relative drop (default 10%)

    Returns:
        True if overfitting is detected (sealed significantly worse)
    """
    if dev_success == 0:
        return False  # Can't detect overfitting with 0% baseline
    relative_drop = (dev_success - sealed_success) / dev_success
    return relative_drop > threshold


# ===================================================================
# Test Suites
# ===================================================================


class TestSealedMetric:
    """Test SealedMetric dataclass methods."""

    def test_sealed_metric_creation(self):
        """Test creating a SealedMetric instance."""
        metric = SealedMetric(
            config_label="Config2_F",
            success_rate=0.85,
            avg_elapsed=2.5,
            avg_input_tokens=150,
            avg_output_tokens=300,
            total_retries=1,
        )
        assert metric.config_label == "Config2_F"
        assert metric.success_rate == 0.85
        assert metric.avg_elapsed == 2.5

    def test_to_dict(self):
        """Test converting SealedMetric to dictionary."""
        metric = SealedMetric(
            config_label="Config3_A",
            success_rate=0.75,
            avg_elapsed=1.8,
            avg_input_tokens=100,
            avg_output_tokens=200,
            total_retries=0,
        )
        d = metric.to_dict()
        assert d["config_label"] == "Config3_A"
        assert d["success_rate"] == 0.75
        assert d["avg_input_tokens"] == 100

    def test_from_dict(self):
        """Test creating SealedMetric from dictionary."""
        d = {
            "config_label": "Config2_F",
            "success_rate": 0.90,
            "avg_elapsed": 3.2,
            "avg_input_tokens": 200,
            "avg_output_tokens": 400,
            "total_retries": 2,
        }
        metric = SealedMetric.from_dict(d)
        assert metric.config_label == "Config2_F"
        assert metric.success_rate == 0.90
        assert metric.total_retries == 2


class TestRelativeImprovement:
    """Test compute_relative_improvement function."""

    def test_normal_improvement(self):
        """Test normal improvement calculation."""
        result = compute_relative_improvement(0.50, 0.75)
        assert result == 0.5  # 50% improvement

    def test_no_improvement(self):
        """Test when rates are equal."""
        result = compute_relative_improvement(0.80, 0.80)
        assert result == 0.0

    def test_decrease(self):
        """Test negative improvement (regression)."""
        result = compute_relative_improvement(0.90, 0.70)
        expected = (0.70 - 0.90) / 0.90
        assert abs(result - expected) < 1e-10  # -22.2%

    def test_zero_base_rate(self):
        """Test edge case when base rate is 0."""
        # Base 0, improved > 0 -> inf
        assert compute_relative_improvement(0.0, 0.5) == float("inf")
        # Base 0, improved 0 -> 0.0
        assert compute_relative_improvement(0.0, 0.0) == 0.0

    def test_small_improvement(self):
        """Test small improvement scenario."""
        result = compute_relative_improvement(0.95, 0.97)
        expected = (0.97 - 0.95) / 0.95
        assert abs(result - expected) < 1e-10


class TestTokenEfficiency:
    """Test compute_token_efficiency_score function."""

    def test_high_success_low_tokens(self):
        """Test high success with low token usage."""
        score = compute_token_efficiency_score(100, 200, True)
        assert score == 0.03  # 300/10000

    def test_low_success_high_tokens(self):
        """Test low success with high token usage."""
        score = compute_token_efficiency_score(500, 800, False)
        assert score == 0.0  # Failed, so 0

    def test_zero_tokens(self):
        """Test when both input and output are 0."""
        score = compute_token_efficiency_score(0, 0, True)
        assert score == 0.0

    def test_max_tokens(self):
        """Test when total tokens equal max."""
        score = compute_token_efficiency_score(5000, 5000, True)
        assert score == 1.0  # 10000/10000


class TestOverfittingDetection:
    """Test detect_overfitting function."""

    def test_no_overfitting(self):
        """Test when sealed performance matches development."""
        assert not detect_overfitting(0.85, 0.83)  # 2.4% drop, below 10% threshold
        assert not detect_overfitting(0.90, 0.85)  # 5.6% drop

    def test_overfitting_detected(self):
        """Test when sealed performance significantly drops."""
        assert detect_overfitting(0.95, 0.80)  # 15.8% drop
        assert detect_overfitting(0.80, 0.60)  # 25% drop

    def test_zero_dev_success(self):
        """Test when development success is 0."""
        # Can't detect overfitting with 0% baseline
        assert not detect_overfitting(0.0, 0.0)
        assert not detect_overfitting(0.0, 0.5)

    def test_sealed_better_than_dev(self):
        """Test when sealed outperforms development."""
        assert not detect_overfitting(0.70, 0.85)  # Sealed is better!

    def test_custom_threshold(self):
        """Test with custom threshold."""
        # With 20% threshold, 15% drop should not trigger
        assert not detect_overfitting(0.90, 0.78, threshold=0.20)
        # But 25% drop should trigger
        assert detect_overfitting(0.90, 0.70, threshold=0.20)


class TestIntegrationMetrics:
    """Integration tests combining multiple metric computations."""

    def test_full_sealed_evaluation_flow(self):
        """Test a complete sealed evaluation scenario."""
        # Simulate results from 3 sealed tasks
        results = [
            {
                "config_label": "Config2_F",
                "success": True,
                "elapsed": 2.1,
                "input": 150,
                "output": 300,
                "retries": 1,
            },
            {
                "config_label": "Config2_F",
                "success": True,
                "elapsed": 2.8,
                "input": 180,
                "output": 350,
                "retries": 0,
            },
            {
                "config_label": "Config2_F",
                "success": False,
                "elapsed": 3.5,
                "input": 200,
                "output": 400,
                "retries": 2,
            },
        ]

        # Compute aggregates
        success_count = sum(1 for r in results if r["success"])
        total_tasks = len(results)
        success_rate = success_count / total_tasks

        avg_elapsed = sum(r["elapsed"] for r in results) / total_tasks
        avg_input = sum(r["input"] for r in results) // total_tasks
        avg_output = sum(r["output"] for r in results) // total_tasks
        total_retries = sum(r["retries"] for r in results)

        # Verify calculations
        assert success_rate == 2.0 / 3.0
        assert abs(avg_elapsed - 2.8) < 0.01
        assert avg_input == 176
        assert avg_output == 350
        assert total_retries == 3

        # Check overfitting with hypothetical dev set performance
        dev_success = 0.85
        overfitting = detect_overfitting(dev_success, success_rate)

        # With 66.7% sealed vs 85% dev, that's a 21.6% drop -> overfitting detected
        assert overfitting
