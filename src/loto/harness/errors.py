class HarnessError(RuntimeError):
    """Base harness error."""


class ConfigurationError(HarnessError):
    """Raised when a configuration is invalid."""


class EngineUnavailable(HarnessError):
    """Raised when an inference engine cannot be reached."""


class CertificationError(HarnessError):
    """Raised when a model certification step fails."""


class UnsafeOperation(HarnessError):
    """Raised when a path or command violates the safety policy."""


class LoopLimitReached(HarnessError):
    """Raised when the engineering loop exceeds a configured limit."""
