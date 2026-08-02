"""Tests for RetryManager and error classification."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from loto_ops.pipeline.retry_manager import RetryManager


class TestRetryManager:
    """Test RetryManager functionality."""

    def test_should_retry_first_attempt(self):
        """Test that first attempt should retry."""
        manager = RetryManager()
        assert manager.should_retry("test_stage", ValueError("test error")) is True

    def test_should_retry_second_attempt(self):
        """Test that second attempt should retry."""
        manager = RetryManager()
        manager.should_retry("test_stage", ValueError("first error"))
        assert manager.should_retry("test_stage", ValueError("second error")) is True

    def test_should_not_retry_after_max_retries(self):
        """Test that retries stop after max retries."""
        manager = RetryManager()
        manager.should_retry("test_stage", ValueError("error 1"))
        manager.should_retry("test_stage", ValueError("error 2"))
        manager.should_retry("test_stage", ValueError("error 3"))
        # 4th attempt should not retry
        assert manager.should_retry("test_stage", ValueError("error 4")) is False

    def test_should_not_retry_same_error_consecutive(self):
        """Test that consecutive same errors stop retrying."""
        manager = RetryManager()
        error = ValueError("same error")
        manager.should_retry("test_stage", error)
        # Same error again should stop retrying
        assert manager.should_retry("test_stage", error) is False

    def test_should_retry_different_error_after_same_error(self):
        """Test that different error after same error allows retry."""
        manager = RetryManager()
        manager.should_retry("test_stage", ValueError("error 1"))
        manager.should_retry("test_stage", ValueError("error 1"))  # Same error
        # Different error should allow retry
        assert manager.should_retry("test_stage", ValueError("error 2")) is True

    def test_get_stage_stats(self):
        """Test getting stage statistics."""
        manager = RetryManager()
        manager.should_retry("test_stage", ValueError("test error"))

        stats = manager.get_stage_stats("test_stage")
        assert stats["stage"] == "test_stage"
        assert stats["attempts"] == 1
        # Check that error history contains the error
        assert any("test error" in hist for hist in stats["error_history"])
        assert len(stats["error_history"]) == 1

    def test_reset_stage(self):
        """Test resetting stage tracking."""
        manager = RetryManager()
        manager.should_retry("test_stage", ValueError("test error"))
        manager.reset_stage("test_stage")

        stats = manager.get_stage_stats("test_stage")
        assert stats["attempts"] == 0
        assert stats["last_error"] == ""

    def test_reset_all(self):
        """Test resetting all stage tracking."""
        manager = RetryManager()
        manager.should_retry("stage1", ValueError("error 1"))
        manager.should_retry("stage2", ValueError("error 2"))

        manager.reset_all()

        assert manager.get_stage_stats("stage1")["attempts"] == 0
        assert manager.get_stage_stats("stage2")["attempts"] == 0


class TestErrorClassification:
    """Test error classification logic."""

    def test_classify_connection_error(self):
        """Test classifying ConnectionError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(ConnectionError("connection refused")) == "E"

    def test_classify_os_error(self):
        """Test classifying OSError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(OSError("file not found")) == "E"

    def test_classify_file_not_found_error(self):
        """Test classifying FileNotFoundError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(FileNotFoundError("test.txt")) == "E"

    def test_classify_permission_error(self):
        """Test classifying PermissionError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(PermissionError("access denied")) == "E"

    def test_classify_module_not_found_error(self):
        """Test classifying ModuleNotFoundError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(ModuleNotFoundError("no module named 'test'")) == "T"

    def test_classify_import_error(self):
        """Test classifying ImportError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(ImportError("cannot import name")) == "T"

    def test_classify_attribute_error(self):
        """Test classifying AttributeError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(AttributeError("no attribute")) == "T"

    def test_classify_assertion_error(self):
        """Test classifying AssertionError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(AssertionError("assertion failed")) == "V"

    def test_classify_value_error(self):
        """Test classifying ValueError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(ValueError("invalid value")) == "M"

    def test_classify_type_error(self):
        """Test classifying TypeError."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(TypeError("invalid type")) == "M"

    def test_classify_unknown_error(self):
        """Test classifying unknown error."""
        from loto_ops.pipeline.orchestrator import _classify_error

        assert _classify_error(Exception("unknown error")) == "U"
