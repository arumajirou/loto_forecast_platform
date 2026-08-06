from __future__ import annotations

from loto.orchestration.pipeline_downstream_effects_common import DownstreamCommitConfig
from loto.orchestration.pipeline_downstream_effects_event import EventEffectsMixin
from loto.orchestration.pipeline_downstream_effects_legacy import (
    LegacyRegistryEffectsMixin,
)
from loto.orchestration.pipeline_downstream_effects_platform import (
    PlatformRegistryEffectsMixin,
)
from loto.orchestration.pipeline_downstream_effects_storage import StorageEffectsMixin


class DefaultDownstreamEffects(
    StorageEffectsMixin,
    LegacyRegistryEffectsMixin,
    PlatformRegistryEffectsMixin,
    EventEffectsMixin,
):
    """Idempotent adapters around the repository's existing downstream APIs."""

    def __init__(self, config: DownstreamCommitConfig):
        self.config = config


__all__ = [
    "DefaultDownstreamEffects",
    "DownstreamCommitConfig",
]
