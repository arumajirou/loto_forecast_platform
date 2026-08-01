from __future__ import annotations

import pandas as pd


def point_in_time_join(
    observations: pd.DataFrame,
    features: pd.DataFrame,
    *,
    entity_keys: tuple[str, ...],
    observation_time: str,
    feature_time: str,
) -> pd.DataFrame:
    if not entity_keys:
        raise ValueError("entity_keys must not be empty")
    left = observations.copy()
    right = features.copy()
    left[observation_time] = pd.to_datetime(left[observation_time], utc=True)
    right[feature_time] = pd.to_datetime(right[feature_time], utc=True)
    if right.duplicated([*entity_keys, feature_time]).any():
        raise ValueError("duplicate entity/feature_time rows")
    left = left.sort_values([*entity_keys, observation_time])
    right = right.sort_values([*entity_keys, feature_time])
    joined = pd.merge_asof(
        left,
        right,
        left_on=observation_time,
        right_on=feature_time,
        by=list(entity_keys),
        direction="backward",
        allow_exact_matches=True,
    )
    if (joined[feature_time] > joined[observation_time]).fillna(False).any():
        raise AssertionError("point-in-time violation detected")
    return joined
