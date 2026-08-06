"""Strict configuration foundation for new workflows."""

from .contracts import CONFIG_SCHEMA_VERSION, StrictFoundationConfig
from .loader import ResolvedConfig, load_config, resolve_payload, write_resolved_config

__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "StrictFoundationConfig",
    "ResolvedConfig",
    "load_config",
    "resolve_payload",
    "write_resolved_config",
]
