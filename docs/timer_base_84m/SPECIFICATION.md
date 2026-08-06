# Specification

The strict request and response models use Pydantic v2 with `extra=forbid`, strict types,
frozen instances, and assignment validation. The request binds package, source, model,
weight, license, game geometry, context geometry, chronology, device request, and artifact
paths. The PR-A response cannot contain forecasts, quantiles, samples, runtime PID, GPU UUID,
or VRAM evidence because no runtime operation is certified.

Unknown fields, unsafe paths, non-finite input, wrong provenance, unsupported layouts,
unsupported covariates, invalid context geometry, and chronology violations fail closed.
