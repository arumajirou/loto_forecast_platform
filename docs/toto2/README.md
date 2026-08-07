# Toto 2.0 4M isolated provider foundation

Status: `PARTIALLY_VERIFIED / P0_P2_IMPLEMENTED / REAL_ISOLATED_RUNTIME_PENDING`.

This directory defines the Toto 2.0 4M contract foundation without changing the root dependency
or shared provider registries. The implementation pins `Datadog/Toto-2.0-4m` at revision
`8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9`, retains all native q0.1 through q0.9 forecasts,
and uses q0.5 as the point forecast.

P0-P2 validate requests, game geometry, native output shape, finite values, quantile ordering,
series identity, provenance, and device evidence. Actual package loading and inference must run in
the separate Python 3.12 lane and are not claimed by this change.
