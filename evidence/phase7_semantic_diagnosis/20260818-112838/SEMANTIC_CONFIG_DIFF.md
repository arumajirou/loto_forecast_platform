# Phase 7 Semantic Config Diagnosis

- Status: **PASS**
- Classification: **SERIALIZATION_ONLY**
- Holdout draws accessed: **0**
- Actuals accessed: **0**

## Reason

Raw serialized configs differ only by unstable representation while canonical semantic values, best trial/objective, trial sequence, and environment match.

## Raw differences

- `$.mlf_init_params.target_transforms[0]` VALUE: `<mlforecast.target_transforms.Differences object at 0x000002785DF348A0>` -> `<mlforecast.target_transforms.Differences object at 0x00000211030A29E0>`
- `$.mlf_init_params.target_transforms[1]` VALUE: `<mlforecast.target_transforms.LocalStandardScaler object at 0x000002785F2B8590>` -> `<mlforecast.target_transforms.LocalStandardScaler object at 0x0000021103063B30>`

## Canonical differences

- None

## Next action

Implement and separately review a versioned canonical semantic serializer; keep Holdout sealed until that verifier change is independently verified.
