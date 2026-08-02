"""Retry manager for preventing infinite self-reflection loops.

Provides retry control with automatic failure classification and stop conditions.
Prevents the AI agent from getting stuck in infinite retry loops on identical errors.
"""

import logging
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger("loto_ops.pipeline.retry_manager")


@dataclass
class RetryManager:
    """Manages retry logic for pipeline stages.

    State:
        - tracks attempt count per stage
        - tracks the last error message for each stage
        - enforces a maximum of 3 retries per stage
        - stops retrying if the same error occurs consecutively (stop condition)
    """

    MAX_RETRIES = 3

    # Error classification mapping
    ERROR_CLASS_MAP: ClassVar[dict[str, list[type[Exception]]]] = {
        # E: Environment errors
        "E": [ConnectionError, OSError, FileNotFoundError, PermissionError],
        # T: Tooling/Parser errors
        "T": [ModuleNotFoundError, ImportError, AttributeError],
        # V: Validator/Test errors
        "V": [AssertionError],
        # M: Model errors
        "M": [ValueError, TypeError],
        # U: Unknown (catch-all for other exceptions)
        "U": [],
    }

    def __init__(self) -> None:
        """Initialize RetryManager with empty stage tracking."""
        self._stage_attempts: dict[str, int] = {}
        self._stage_last_error: dict[str, str] = {}
        self._stage_error_history: dict[str, list[str]] = {}

    def should_retry(self, stage_name: str, error: Exception) -> bool:
        """Determine if a stage should be retried based on error classification.

        Args:
            stage_name: Name of the pipeline stage
            error: The exception that occurred

        Returns:
            True if retry is allowed, False if retry should be stopped
        """
        # Get current attempt count
        current_attempt = self._stage_attempts.get(stage_name, 0) + 1
        self._stage_attempts[stage_name] = current_attempt

        # Track error history
        error_msg = str(error)
        if stage_name not in self._stage_error_history:
            self._stage_error_history[stage_name] = []
        self._stage_error_history[stage_name].append(error_msg)

        # Check stop condition: if same error occurred consecutively, stop retrying
        if len(self._stage_error_history[stage_name]) >= 2:
            recent_errors = self._stage_error_history[stage_name][-2:]
            if recent_errors[0] == recent_errors[1]:
                logger.warning(
                    f"Stop condition triggered for stage '{stage_name}': "
                    f"same error occurred consecutively. Error: {error_msg}"
                )
                return False

        # Check maximum retries
        if current_attempt > self.MAX_RETRIES:
            logger.warning(
                f"Maximum retries ({self.MAX_RETRIES}) exceeded for stage '{stage_name}'"
            )
            return False

        # Log retry attempt
        logger.info(
            f"Retry allowed for stage '{stage_name}': attempt {current_attempt}/{self.MAX_RETRIES}"
        )
        return True

    def get_error_class(self, error: Exception) -> str:
        """Classify an error into one of M, H, T, R, V, E, U categories.

        Args:
            error: The exception to classify

        Returns:
            Single character class identifier (M, H, T, R, V, E, U)
        """
        for class_name, error_types in self.ERROR_CLASS_MAP.items():
            if error_types and isinstance(error, tuple(error_types)):
                return class_name
        return "U"  # Unknown

    def get_stage_stats(self, stage_name: str) -> dict:
        """Get statistics for a specific stage.

        Args:
            stage_name: Name of the pipeline stage

        Returns:
            Dictionary with attempt count and last error message
        """
        return {
            "stage": stage_name,
            "attempts": self._stage_attempts.get(stage_name, 0),
            "last_error": self._stage_last_error.get(stage_name, ""),
            "error_history": self._stage_error_history.get(stage_name, []),
        }

    def reset_stage(self, stage_name: str) -> None:
        """Reset tracking for a specific stage.

        Args:
            stage_name: Name of the pipeline stage to reset
        """
        self._stage_attempts[stage_name] = 0
        self._stage_last_error[stage_name] = ""
        self._stage_error_history[stage_name] = []

    def reset_all(self) -> None:
        """Reset all stage tracking."""
        self._stage_attempts.clear()
        self._stage_last_error.clear()
        self._stage_error_history.clear()
