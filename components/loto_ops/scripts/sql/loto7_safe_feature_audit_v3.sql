WITH ordered AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER w AS rn,
        LAG(y, 1)  OVER w AS expected_lag_1,
        LAG(y, 2)  OVER w AS expected_lag_2,
        LAG(y, 3)  OVER w AS expected_lag_3,
        LAG(y, 7)  OVER w AS expected_lag_7,
        LAG(y, 14) OVER w AS expected_lag_14,
        LAG(y, 28) OVER w AS expected_lag_28,
        MIN(ds::date) OVER (PARTITION BY unique_id) AS first_ds,
        AVG(y) OVER (PARTITION BY unique_id) AS full_sample_mean
    FROM exog.loto_y_ts_exog e
    WHERE loto = 'loto7'
      AND ts_type = 'raw'
    WINDOW w AS (
        PARTITION BY unique_id
        ORDER BY ds
    )
),
expected AS (
    SELECT
        ordered.*,

        CASE WHEN rn > 3 THEN
            AVG(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_mean_3,

        CASE WHEN rn > 7 THEN
            AVG(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_mean_7,

        CASE WHEN rn > 14 THEN
            AVG(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_mean_14,

        CASE WHEN rn > 28 THEN
            AVG(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_mean_28,

        CASE WHEN rn > 7 THEN
            STDDEV_SAMP(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_std_7,

        CASE WHEN rn > 14 THEN
            STDDEV_SAMP(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_std_14,

        CASE WHEN rn > 28 THEN
            STDDEV_SAMP(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_std_28,

        CASE WHEN rn > 7 THEN
            MIN(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_min_7,

        CASE WHEN rn > 7 THEN
            MAX(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_max_7,

        CASE WHEN rn > 14 THEN
            MIN(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_min_14,

        CASE WHEN rn > 14 THEN
            MAX(y) OVER (
                PARTITION BY unique_id ORDER BY ds
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            )
        END AS expected_roll_max_14,

        AVG(y) OVER (
            PARTITION BY unique_id ORDER BY ds
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS expected_expanding_mean,

        STDDEV_SAMP(y) OVER (
            PARTITION BY unique_id ORDER BY ds
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS expected_expanding_std

    FROM ordered
),
duplicates AS (
    SELECT COUNT(*) AS n
    FROM (
        SELECT unique_id, ds::date, ts_type, COUNT(*)
        FROM exog.loto_y_ts_exog
        WHERE loto = 'loto7'
          AND ts_type = 'raw'
        GROUP BY unique_id, ds::date, ts_type
        HAVING COUNT(*) > 1
    ) q
),
dates AS (
    SELECT
        (
            SELECT MAX(ds)::date
            FROM exog.loto_y_ts_exog
            WHERE loto='loto7' AND ts_type='raw'
        ) AS source_last_date,
        (
            SELECT MAX(ds)::date
            FROM dataset.loto_y_ts
            WHERE loto='loto7' AND ts_type='raw'
        ) AS target_last_date
),
metrics AS (
    SELECT
        COUNT(*) AS rows_checked,
        COUNT(DISTINCT unique_id) AS series_count,

        COUNT(*) FILTER (WHERE
            (hist_lag_1 IS NULL) <> (expected_lag_1 IS NULL)
            OR (
                hist_lag_1 IS NOT NULL
                AND expected_lag_1 IS NOT NULL
                AND ABS(hist_lag_1 - expected_lag_1) > 1e-9
            )
        ) AS lag1_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_lag_2 IS NULL) <> (expected_lag_2 IS NULL)
            OR (
                hist_lag_2 IS NOT NULL
                AND expected_lag_2 IS NOT NULL
                AND ABS(hist_lag_2 - expected_lag_2) > 1e-9
            )
        ) AS lag2_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_lag_3 IS NULL) <> (expected_lag_3 IS NULL)
            OR (
                hist_lag_3 IS NOT NULL
                AND expected_lag_3 IS NOT NULL
                AND ABS(hist_lag_3 - expected_lag_3) > 1e-9
            )
        ) AS lag3_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_lag_7 IS NULL) <> (expected_lag_7 IS NULL)
            OR (
                hist_lag_7 IS NOT NULL
                AND expected_lag_7 IS NOT NULL
                AND ABS(hist_lag_7 - expected_lag_7) > 1e-9
            )
        ) AS lag7_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_lag_14 IS NULL) <> (expected_lag_14 IS NULL)
            OR (
                hist_lag_14 IS NOT NULL
                AND expected_lag_14 IS NOT NULL
                AND ABS(hist_lag_14 - expected_lag_14) > 1e-9
            )
        ) AS lag14_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_lag_28 IS NULL) <> (expected_lag_28 IS NULL)
            OR (
                hist_lag_28 IS NOT NULL
                AND expected_lag_28 IS NOT NULL
                AND ABS(hist_lag_28 - expected_lag_28) > 1e-9
            )
        ) AS lag28_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_mean_3 IS NULL) <> (expected_roll_mean_3 IS NULL)
            OR (
                hist_roll_mean_3 IS NOT NULL
                AND expected_roll_mean_3 IS NOT NULL
                AND ABS(hist_roll_mean_3 - expected_roll_mean_3) > 1e-9
            )
        ) AS roll_mean3_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_mean_7 IS NULL) <> (expected_roll_mean_7 IS NULL)
            OR (
                hist_roll_mean_7 IS NOT NULL
                AND expected_roll_mean_7 IS NOT NULL
                AND ABS(hist_roll_mean_7 - expected_roll_mean_7) > 1e-9
            )
        ) AS roll_mean7_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_mean_14 IS NULL) <> (expected_roll_mean_14 IS NULL)
            OR (
                hist_roll_mean_14 IS NOT NULL
                AND expected_roll_mean_14 IS NOT NULL
                AND ABS(hist_roll_mean_14 - expected_roll_mean_14) > 1e-9
            )
        ) AS roll_mean14_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_mean_28 IS NULL) <> (expected_roll_mean_28 IS NULL)
            OR (
                hist_roll_mean_28 IS NOT NULL
                AND expected_roll_mean_28 IS NOT NULL
                AND ABS(hist_roll_mean_28 - expected_roll_mean_28) > 1e-9
            )
        ) AS roll_mean28_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_expanding_mean IS NULL) <> (expected_expanding_mean IS NULL)
            OR (
                hist_expanding_mean IS NOT NULL
                AND expected_expanding_mean IS NOT NULL
                AND ABS(hist_expanding_mean - expected_expanding_mean) > 1e-9
            )
        ) AS expanding_mean_mismatches,

        COUNT(*) FILTER (
            WHERE feat_year <> EXTRACT(YEAR FROM ds)::bigint
        ) AS calendar_year_mismatches,

        COUNT(*) FILTER (
            WHERE feat_month <> EXTRACT(MONTH FROM ds)::bigint
        ) AS calendar_month_mismatches,

        COUNT(*) FILTER (
            WHERE feat_day <> EXTRACT(DAY FROM ds)::bigint
        ) AS calendar_day_mismatches,

        COUNT(*) FILTER (
            WHERE feat_dayofweek <> (EXTRACT(ISODOW FROM ds)::bigint - 1)
        ) AS calendar_dow_mismatches,

        COUNT(*) FILTER (
            WHERE feat_weekofyear <> EXTRACT(WEEK FROM ds)::bigint
        ) AS calendar_week_mismatches,

        COUNT(*) FILTER (
            WHERE feat_dayofyear <> EXTRACT(DOY FROM ds)::bigint
        ) AS calendar_doy_mismatches,

        COUNT(*) FILTER (
            WHERE feat_is_weekend <>
                CASE WHEN EXTRACT(ISODOW FROM ds)::int IN (6, 7) THEN 1 ELSE 0 END
        ) AS calendar_weekend_mismatches,

        COUNT(*) FILTER (
            WHERE feat_is_month_start <>
                CASE WHEN EXTRACT(DAY FROM ds)::int = 1 THEN 1 ELSE 0 END
        ) AS calendar_month_start_mismatches,

        COUNT(*) FILTER (
            WHERE feat_is_month_end <>
                CASE
                    WHEN ds::date =
                         (date_trunc('month', ds) + interval '1 month - 1 day')::date
                    THEN 1 ELSE 0
                END
        ) AS calendar_month_end_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_std_7 IS NULL) <> (expected_roll_std_7 IS NULL)
            OR (
                hist_roll_std_7 IS NOT NULL
                AND expected_roll_std_7 IS NOT NULL
                AND ABS(hist_roll_std_7 - expected_roll_std_7) > 1e-9
            )
        ) AS roll_std7_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_std_14 IS NULL) <> (expected_roll_std_14 IS NULL)
            OR (
                hist_roll_std_14 IS NOT NULL
                AND expected_roll_std_14 IS NOT NULL
                AND ABS(hist_roll_std_14 - expected_roll_std_14) > 1e-9
            )
        ) AS roll_std14_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_std_28 IS NULL) <> (expected_roll_std_28 IS NULL)
            OR (
                hist_roll_std_28 IS NOT NULL
                AND expected_roll_std_28 IS NOT NULL
                AND ABS(hist_roll_std_28 - expected_roll_std_28) > 1e-9
            )
        ) AS roll_std28_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_min_7 IS NULL) <> (expected_roll_min_7 IS NULL)
            OR (
                hist_roll_min_7 IS NOT NULL
                AND expected_roll_min_7 IS NOT NULL
                AND ABS(hist_roll_min_7 - expected_roll_min_7) > 1e-9
            )
        ) AS roll_min7_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_max_7 IS NULL) <> (expected_roll_max_7 IS NULL)
            OR (
                hist_roll_max_7 IS NOT NULL
                AND expected_roll_max_7 IS NOT NULL
                AND ABS(hist_roll_max_7 - expected_roll_max_7) > 1e-9
            )
        ) AS roll_max7_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_min_14 IS NULL) <> (expected_roll_min_14 IS NULL)
            OR (
                hist_roll_min_14 IS NOT NULL
                AND expected_roll_min_14 IS NOT NULL
                AND ABS(hist_roll_min_14 - expected_roll_min_14) > 1e-9
            )
        ) AS roll_min14_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_roll_max_14 IS NULL) <> (expected_roll_max_14 IS NULL)
            OR (
                hist_roll_max_14 IS NOT NULL
                AND expected_roll_max_14 IS NOT NULL
                AND ABS(hist_roll_max_14 - expected_roll_max_14) > 1e-9
            )
        ) AS roll_max14_mismatches,

        COUNT(*) FILTER (WHERE
            (hist_expanding_std IS NULL) <> (expected_expanding_std IS NULL)
            OR (
                hist_expanding_std IS NOT NULL
                AND expected_expanding_std IS NOT NULL
                AND ABS(hist_expanding_std - expected_expanding_std) > 1e-9
            )
        ) AS expanding_std_mismatches,

        COUNT(*) FILTER (
            WHERE feat_days_since_first <> (ds::date - first_ds)
        ) AS days_since_first_mismatches,

        COUNT(*) FILTER (
            WHERE feat_row_no_in_group <> rn
        ) AS row_no_mismatches,

        COUNT(*) FILTER (
            WHERE expected_lag_1 IS NOT NULL
              AND ABS(hist_diff_1 - (y - expected_lag_1)) < 1e-9
        ) AS leak_diff1_uses_current_y,

        COUNT(*) FILTER (
            WHERE expected_lag_7 IS NOT NULL
              AND ABS(hist_diff_7 - (y - expected_lag_7)) < 1e-9
        ) AS leak_diff7_uses_current_y,

        COUNT(*) FILTER (
            WHERE ABS(stat_y_mean - full_sample_mean) < 1e-9
        ) AS leak_stat_mean_full_sample

    FROM expected
)
SELECT
    m.rows_checked,
    m.series_count,
    d.n AS duplicate_keys,
    dates.source_last_date,
    dates.target_last_date,
    COUNT(*) FILTER (
        WHERE e.ds::date = dates.target_last_date
    ) AS latest_rows,
    COUNT(DISTINCT e.unique_id) FILTER (
        WHERE e.ds::date = dates.target_last_date
    ) AS latest_series,

    m.lag1_mismatches,
    m.lag2_mismatches,
    m.lag3_mismatches,
    m.lag7_mismatches,
    m.lag14_mismatches,
    m.lag28_mismatches,

    m.roll_mean3_mismatches,
    m.roll_mean7_mismatches,
    m.roll_mean14_mismatches,
    m.roll_mean28_mismatches,
    m.expanding_mean_mismatches,

    m.calendar_year_mismatches,
    m.calendar_month_mismatches,
    m.calendar_day_mismatches,
    m.calendar_dow_mismatches,
    m.calendar_week_mismatches,
    m.calendar_doy_mismatches,
    m.calendar_weekend_mismatches,
    m.calendar_month_start_mismatches,
    m.calendar_month_end_mismatches,

    m.roll_std7_mismatches,
    m.roll_std14_mismatches,
    m.roll_std28_mismatches,
    m.roll_min7_mismatches,
    m.roll_max7_mismatches,
    m.roll_min14_mismatches,
    m.roll_max14_mismatches,
    m.expanding_std_mismatches,
    m.days_since_first_mismatches,
    m.row_no_mismatches,

    m.leak_diff1_uses_current_y,
    m.leak_diff7_uses_current_y,
    m.leak_stat_mean_full_sample

FROM metrics m
CROSS JOIN duplicates d
CROSS JOIN dates
CROSS JOIN expected e
GROUP BY
    m.rows_checked,
    m.series_count,
    d.n,
    dates.source_last_date,
    dates.target_last_date,

    m.lag1_mismatches,
    m.lag2_mismatches,
    m.lag3_mismatches,
    m.lag7_mismatches,
    m.lag14_mismatches,
    m.lag28_mismatches,

    m.roll_mean3_mismatches,
    m.roll_mean7_mismatches,
    m.roll_mean14_mismatches,
    m.roll_mean28_mismatches,
    m.expanding_mean_mismatches,

    m.calendar_year_mismatches,
    m.calendar_month_mismatches,
    m.calendar_day_mismatches,
    m.calendar_dow_mismatches,
    m.calendar_week_mismatches,
    m.calendar_doy_mismatches,
    m.calendar_weekend_mismatches,
    m.calendar_month_start_mismatches,
    m.calendar_month_end_mismatches,

    m.roll_std7_mismatches,
    m.roll_std14_mismatches,
    m.roll_std28_mismatches,
    m.roll_min7_mismatches,
    m.roll_max7_mismatches,
    m.roll_min14_mismatches,
    m.roll_max14_mismatches,
    m.expanding_std_mismatches,
    m.days_since_first_mismatches,
    m.row_no_mismatches,

    m.leak_diff1_uses_current_y,
    m.leak_diff7_uses_current_y,
    m.leak_stat_mean_full_sample;
