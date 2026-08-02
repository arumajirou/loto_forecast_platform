BEGIN;

CREATE SCHEMA IF NOT EXISTS exog;

CREATE TABLE IF NOT EXISTS exog.loto7_exog_safe_v3 (
    feature_contract text NOT NULL,
    loto text NOT NULL,
    unique_id text NOT NULL,
    ts_type text NOT NULL,
    ds timestamp without time zone NOT NULL,
    target_y double precision,

    feat_year bigint,
    feat_month bigint,
    feat_day bigint,
    feat_dayofweek bigint,
    feat_weekofyear bigint,
    feat_dayofyear bigint,
    feat_is_weekend bigint,
    feat_is_month_start bigint,
    feat_is_month_end bigint,
    feat_days_since_first bigint,
    feat_row_no_in_group bigint,

    hist_lag_1 double precision,
    hist_lag_2 double precision,
    hist_lag_3 double precision,
    hist_lag_7 double precision,
    hist_lag_14 double precision,
    hist_lag_28 double precision,

    hist_roll_mean_3 double precision,
    hist_roll_mean_7 double precision,
    hist_roll_mean_14 double precision,
    hist_roll_mean_28 double precision,

    hist_roll_std_7 double precision,
    hist_roll_std_14 double precision,
    hist_roll_std_28 double precision,

    hist_roll_min_7 double precision,
    hist_roll_max_7 double precision,
    hist_roll_min_14 double precision,
    hist_roll_max_14 double precision,

    hist_expanding_mean double precision,
    hist_expanding_std double precision
);

TRUNCATE TABLE exog.loto7_exog_safe_v3;

INSERT INTO exog.loto7_exog_safe_v3 (
    feature_contract,
    loto,
    unique_id,
    ts_type,
    ds,
    target_y,
    feat_year,
    feat_month,
    feat_day,
    feat_dayofweek,
    feat_weekofyear,
    feat_dayofyear,
    feat_is_weekend,
    feat_is_month_start,
    feat_is_month_end,
    feat_days_since_first,
    feat_row_no_in_group,
    hist_lag_1,
    hist_lag_2,
    hist_lag_3,
    hist_lag_7,
    hist_lag_14,
    hist_lag_28,
    hist_roll_mean_3,
    hist_roll_mean_7,
    hist_roll_mean_14,
    hist_roll_mean_28,
    hist_roll_std_7,
    hist_roll_std_14,
    hist_roll_std_28,
    hist_roll_min_7,
    hist_roll_max_7,
    hist_roll_min_14,
    hist_roll_max_14,
    hist_expanding_mean,
    hist_expanding_std
)
SELECT
    'loto7-safe-v3',
    loto,
    unique_id,
    ts_type,
    ds,
    y AS target_y,
    feat_year,
    feat_month,
    feat_day,
    feat_dayofweek,
    feat_weekofyear,
    feat_dayofyear,
    feat_is_weekend,
    feat_is_month_start,
    feat_is_month_end,
    feat_days_since_first,
    feat_row_no_in_group,
    hist_lag_1,
    hist_lag_2,
    hist_lag_3,
    hist_lag_7,
    hist_lag_14,
    hist_lag_28,
    hist_roll_mean_3,
    hist_roll_mean_7,
    hist_roll_mean_14,
    hist_roll_mean_28,
    hist_roll_std_7,
    hist_roll_std_14,
    hist_roll_std_28,
    hist_roll_min_7,
    hist_roll_max_7,
    hist_roll_min_14,
    hist_roll_max_14,
    hist_expanding_mean,
    hist_expanding_std
FROM exog.loto_y_ts_exog
WHERE loto = 'loto7'
  AND ts_type = 'raw';

CREATE UNIQUE INDEX IF NOT EXISTS
    loto7_exog_safe_v3_key_idx
ON exog.loto7_exog_safe_v3 (loto, unique_id, ts_type, ds);

CREATE INDEX IF NOT EXISTS
    loto7_exog_safe_v3_ds_idx
ON exog.loto7_exog_safe_v3 (ds);

COMMENT ON TABLE exog.loto7_exog_safe_v3 IS
'Physical leakage-audited Loto7 feature table. Rolling features use shift=1 '
'and full-window min_periods. Refreshed only after the v3 audit passes.';

ANALYZE exog.loto7_exog_safe_v3;

COMMIT;
