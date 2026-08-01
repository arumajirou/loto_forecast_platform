from __future__ import annotations

# ruff: noqa: E501
from loto.models.catalog import ModelSpec
from loto.models.providers.base import FoundationProvider, FoundationProviderError
from loto.models.providers.chronos import ChronosProvider
from loto.models.providers.granite_ttm import GraniteTTMProvider
from loto.models.providers.moirai import MoiraiProvider
from loto.models.providers.sundial import SundialProvider
from loto.models.providers.tabpfn_ts import TabPFNTSProvider
from loto.models.providers.timesfm import TimesFMProvider
from loto.models.providers.tirex import TiRexProvider


class ProviderNotImplemented(FoundationProvider):
    def validate_environment(self) -> dict:
        raise FoundationProviderError(
            "PROVIDER_NOT_IMPLEMENTED",
            f"foundation provider is not implemented for {self.spec.model_id}",
        )

    def load(self) -> ProviderNotImplemented:
        self.validate_environment()
        return self

    def predict(self, history):
        self.validate_environment()


FOUNDATION_PROVIDERS: dict[str, type[FoundationProvider]] = {
    "chronos": ChronosProvider,
    "chronos-bolt-tiny": ChronosProvider,
    "chronos-t5-small": ChronosProvider,
    "chronos-2-small": ChronosProvider,
    "sundial": SundialProvider,
    "timesfm": TimesFMProvider,
    "timesfm-2.5": TimesFMProvider,
    "granite-ttm": GraniteTTMProvider,
    "tirex": TiRexProvider,
    "moirai": MoiraiProvider,
    "tabpfn-ts": TabPFNTSProvider,
}


def get_foundation_provider(spec: ModelSpec) -> type[FoundationProvider]:
    return FOUNDATION_PROVIDERS.get(spec.model_id) or FOUNDATION_PROVIDERS.get(
        spec.library, ProviderNotImplemented
    )
