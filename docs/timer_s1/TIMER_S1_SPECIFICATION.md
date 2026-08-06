# Timer-S1 specification

Timer-S1 is represented as an isolated TSFM provider with a strict Pydantic v2 boundary.
The native request geometry is `[series, context]`. The expected native forecast geometry is
`[series, 9, horizon]`. Project point forecasts are copied from q0.5; all quantiles remain separate.

The PR-A provider implements identity, request validation, provenance validation, structural
geometry compilation, chronology evidence, remote-code policy validation, and normalized failure
responses. Real model import, load, generation, save/reload, device proof, and GPU evidence
are PR-B.
