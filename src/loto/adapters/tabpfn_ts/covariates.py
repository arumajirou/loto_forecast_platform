from __future__ import annotations

from enum import StrEnum


class CovariateKind(StrEnum):
    KNOWN_FUTURE_DYNAMIC = "known_future_dynamic"
    PAST_ONLY_DYNAMIC = "past_only_dynamic"
    STATIC = "static"
    CALENDAR_ENGINEERED = "calendar_engineered"


class CovariateSupport(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED_BY_UPSTREAM = "UNSUPPORTED_BY_UPSTREAM"


COVARIATE_SUPPORT: dict[CovariateKind, CovariateSupport] = {
    CovariateKind.KNOWN_FUTURE_DYNAMIC: CovariateSupport.SUPPORTED,
    CovariateKind.PAST_ONLY_DYNAMIC: CovariateSupport.UNSUPPORTED_BY_UPSTREAM,
    CovariateKind.STATIC: CovariateSupport.UNSUPPORTED_BY_UPSTREAM,
    CovariateKind.CALENDAR_ENGINEERED: CovariateSupport.SUPPORTED,
}


def require_supported_covariate(kind: CovariateKind) -> None:
    support = COVARIATE_SUPPORT[kind]
    if support is not CovariateSupport.SUPPORTED:
        raise ValueError(f"{support.value}: {kind.value}")
