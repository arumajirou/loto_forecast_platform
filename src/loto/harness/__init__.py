"""Local multi-model harness for loto_forecast_platform.

The package deliberately separates model inference from repository mutation.
Inference engines are HTTP clients; repository writes remain the responsibility
of a bounded loop executor or an external coding agent such as Claude Code.
"""

from .contracts import HarnessStatus, ModelDescriptor

__all__ = ["HarnessStatus", "ModelDescriptor"]
