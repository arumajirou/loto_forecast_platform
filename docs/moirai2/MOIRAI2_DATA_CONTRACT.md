# Moirai 2.0 Data Contract

`history` is an ordered list of rows whose keys exactly equal `position_columns`. Draw-sequence
mode maps one draw to one synthetic daily period and stores the deterministic mapping hash.
Calendar-time mode builds a daily grid and preserves missing dates as NaN.

Past-only covariates contain exactly history-length values. Known-future covariates contain
history plus horizon values and require matching `known_at_prediction_time` evidence for every
feature name; absent evidence, revealed-only values, or mismatched chronology is rejected. Formal evaluation remains time ordered and is not implemented in this increment.
