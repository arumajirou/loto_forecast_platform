BEGIN;

CREATE SCHEMA IF NOT EXISTS exog;

CREATE TABLE IF NOT EXISTS exog.loto7_exog_safe_v2 (
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

    hist_expanding_mean double precision
);

TRUNCATE TABLE exog.loto7_exog_safe_v2;

INSERT INTO exog.loto7_exog_safe_v2 (
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
    hist_expanding_mean
)
SELECT
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
    hist_expanding_mean
FROM exog.loto_y_ts_exog
WHERE loto = 'loto7'
  AND ts_type = 'raw';

CREATE UNIQUE INDEX IF NOT EXISTS
    loto7_exog_safe_v2_key_idx
ON exog.loto7_exog_safe_v2 (loto, unique_id, ts_type, ds);

CREATE INDEX IF NOT EXISTS
    loto7_exog_safe_v2_ds_idx
ON exog.loto7_exog_safe_v2 (ds);

COMMENT ON TABLE exog.loto7_exog_safe_v2 IS
'Leakage-audited physical Loto7 feature table. Refreshed after build-exog. '
'Do not replace with a view over exog.loto_y_ts_exog because that source table '
'is dropped and recreated by the writer.';

ANALYZE exog.loto7_exog_safe_v2;

COMMIT;
