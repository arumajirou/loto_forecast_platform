"""Tests for workflow metrics aggregation and calculation."""

import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the workflow metrics functions from workflow_comparison
try:
    from benchmarks.workflow_comparison import (
        WorkflowResult,
        WorkflowSummary,
        aggregate_workflow_results,
        compare_workflows,
    )

    HAS_WORKFLOW = True
except ImportError:
    HAS_WORKFLOW = False


class TestWorkflowMetrics:
    """Test workflow metrics aggregation logic."""

    def setup_method(self):
        """Setup test data."""
        if not HAS_WORKFLOW:
            pytest.skip("workflow_comparison module not available")

    def test_aggregate_single_workflow(self):
        """Test aggregation with single workflow results."""
        results = [
            WorkflowResult(
                workflow_id="A",
                task_index=0,
                task_success_rate=0.85,
                elapsed_seconds=1.5,
                input_tokens=150,
                output_tokens=200,
                tool_call_count=3,
                retry_count=0,
            ),
            WorkflowResult(
                workflow_id="A",
                task_index=1,
                task_success_rate=0.90,
                elapsed_seconds=1.8,
                input_tokens=180,
                output_tokens=250,
                tool_call_count=4,
                retry_count=1,
            ),
        ]

        summaries = aggregate_workflow_results(results)

        assert "A" in summaries
        summary = summaries["A"]
        assert summary.total_tasks == 2
        assert abs(summary.avg_success_rate - 0.875) < 0.01
        assert abs(summary.avg_elapsed_seconds - 1.65) < 0.01
        assert summary.avg_input_tokens == 165
        assert summary.avg_output_tokens == 225
        assert abs(summary.avg_tool_call_count - 3.5) < 0.01
        assert abs(summary.avg_retry_count - 0.5) < 0.01

    def test_aggregate_multiple_workflows(self):
        """Test aggregation across multiple workflows."""
        results = [
            WorkflowResult(
                workflow_id="A",
                task_index=0,
                task_success_rate=0.85,
                elapsed_seconds=1.5,
                input_tokens=150,
                output_tokens=200,
                tool_call_count=3,
                retry_count=0,
            ),
            WorkflowResult(
                workflow_id="B",
                task_index=0,
                task_success_rate=0.92,
                elapsed_seconds=2.1,
                input_tokens=200,
                output_tokens=300,
                tool_call_count=6,
                retry_count=0,
            ),
            WorkflowResult(
                workflow_id="B",
                task_index=1,
                task_success_rate=0.88,
                elapsed_seconds=1.9,
                input_tokens=180,
                output_tokens=280,
                tool_call_count=5,
                retry_count=1,
            ),
        ]

        summaries = aggregate_workflow_results(results)

        assert "A" in summaries
        assert "B" in summaries

        # A has 1 task, B has 2 tasks
        assert summaries["A"].total_tasks == 1
        assert summaries["B"].total_tasks == 2

        # B should have average of two results
        assert abs(summaries["B"].avg_success_rate - 0.90) < 0.01
        assert abs(summaries["B"].avg_elapsed_seconds - 2.0) < 0.01

    def test_compare_workflows_sorting(self):
        """Test that comparison sorts by success rate then elapsed time."""
        summaries = {
            "C": WorkflowSummary(
                workflow_id="C",
                avg_success_rate=0.92,
                avg_elapsed_seconds=2.15,
                avg_input_tokens=230,
                avg_output_tokens=340,
                avg_tool_call_count=6.5,
                avg_retry_count=0.0,
                total_tasks=2,
            ),
            "A": WorkflowSummary(
                workflow_id="A",
                avg_success_rate=0.85,
                avg_elapsed_seconds=1.65,
                avg_input_tokens=165,
                avg_output_tokens=225,
                avg_tool_call_count=3.5,
                avg_retry_count=0.5,
                total_tasks=2,
            ),
            "F": WorkflowSummary(
                workflow_id="F",
                avg_success_rate=0.91,
                avg_elapsed_seconds=1.68,
                avg_input_tokens=195,
                avg_output_tokens=285,
                avg_tool_call_count=4.0,
                avg_retry_count=1.0,
                total_tasks=2,
            ),
        }

        comparison = compare_workflows(summaries)

        # Should be sorted by success rate (descending), then elapsed time (ascending)
        assert len(comparison) == 3
        assert comparison[0]["workflow_id"] == "C"  # Highest success rate
        assert comparison[1]["workflow_id"] == "F"  # Second highest
        assert comparison[2]["workflow_id"] == "A"  # Lowest success rate

    def test_aggregate_empty_results(self):
        """Test aggregation with empty results."""
        summaries = aggregate_workflow_results([])
        assert len(summaries) == 0

    def test_compare_empty_summaries(self):
        """Test comparison with empty summaries."""
        comparison = compare_workflows({})
        assert len(comparison) == 0

    def test_tool_call_efficiency(self):
        """Test tool call efficiency calculation (tokens per tool call)."""
        results = [
            WorkflowResult(
                workflow_id="A",
                task_index=0,
                task_success_rate=0.85,
                elapsed_seconds=1.5,
                input_tokens=150,
                output_tokens=200,
                tool_call_count=5,
                retry_count=0,
            ),
            WorkflowResult(
                workflow_id="A",
                task_index=1,
                task_success_rate=0.90,
                elapsed_seconds=1.8,
                input_tokens=180,
                output_tokens=250,
                tool_call_count=4,
                retry_count=1,
            ),
        ]

        summaries = aggregate_workflow_results(results)
        summary = summaries["A"]

        # Calculate token efficiency using aggregated metrics
        # avg_input = 165, avg_output = 225, avg_tool = 3.5
        total_tokens = summary.avg_input_tokens + summary.avg_output_tokens
        total_tools = summary.avg_tool_call_count
        token_per_tool = total_tokens / total_tools if total_tools > 0 else 0

        # Expected: (165 + 225) / 4.5 = 390 / 4.5 = 86.67
        expected_efficiency = (165 + 225) / 4.5

        assert abs(token_per_tool - expected_efficiency) < 0.1
