# Backward-Compatible Adapter Design

## Principle

Compatibility adapters are read-only and conservative. They map a legacy status into the highest
common status supported by supplied evidence. They never synthesize a human approval, registry
receipt, canary binding, primary authorization, or primary binding.

## Representative mappings

| Legacy source | Legacy status | Common mapping |
|---|---|---|
| main promotion | `PROMOTE_FORMAL` / `PROMOTE_PROVISIONAL` | `RUNTIME_UNVERIFIED` unless separate runtime evidence exists; at most `HUMAN_REVIEW_REQUIRED` |
| sktime P6 | `ELIGIBLE_FOR_HUMAN_APPROVAL` | `HUMAN_REVIEW_REQUIRED` |
| sktime P7 | `APPROVED_NOT_REGISTERED` | exact only with verified signed approval |
| sktime P8 | `REGISTERED_NOT_DEPLOYED` | exact only with committed registry receipt |
| sktime P9 | `CANARY_ACTIVE_NOT_PRIMARY` | exact only with verified shadow binding |
| sktime P10 | `ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW` | exact only with sealed review evidence |
| sktime P11 | `APPROVED_NOT_PRIMARY` | exact only with primary-scope approval evidence |
| NeuralForecast promotion gate | `PASS` | runtime status only; never production approval |
| NeuralForecast scoring | rank or first place | `EVALUATION_PENDING` |
| NeuralForecast experiment registry | `PASS` | `EVALUATION_PENDING`; not production registration |

## PlatformRegistry boundary

A legacy registry entry maps to `REGISTERED_NOT_DEPLOYED` only when a committed receipt binds the
exact common subject. It maps to `PRIMARY_ACTIVE` only when an explicit primary deployment binding
and primary-scope approval are independently verified. An alias, catalog listing, experiment record,
or MLflow run is not enough.

## Migration sequence

1. Select one provider or framework.
2. Construct the common subject from existing immutable evidence without changing it.
3. Compare provider-local and common decisions for identical fixtures.
4. Run illegal-transition and subject-drift tests.
5. Collect real runtime and evaluation evidence.
6. Keep both validators until parity is reviewed.
7. Change a production consumer only in a separate explicitly approved PR.

Provider-specific P6-P12 implementations are not bulk-modified by this foundation.
