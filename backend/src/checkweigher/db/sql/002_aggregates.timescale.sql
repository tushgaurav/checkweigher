-- TimescaleDB variant: hypertable, compression and continuous aggregates.
-- Keep the SELECT lists identical to 002_aggregates.plain.sql.

CREATE EXTENSION IF NOT EXISTS timescaledb;

SELECT create_hypertable('weighing', by_range('ts', INTERVAL '7 days'), migrate_data => true);

ALTER TABLE weighing SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'machine_id',
    timescaledb.compress_orderby = 'ts DESC'
);

SELECT add_compression_policy('weighing', INTERVAL '14 days');

-- Sufficient statistics per 15 minutes x machine x product x shift. Plant/shift/day KPIs are
-- sums of these rows, which makes every aggregate exactly volume-weighted.
-- 15-minute buckets align with local hours for any UTC offset that is a multiple of 15 min.
CREATE MATERIALIZED VIEW weighing_15m
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    time_bucket(INTERVAL '15 minutes', ts) AS bucket,
    machine_id,
    product_id,
    shift_date,
    shift_code,
    count(*)                                                                   AS n,
    count(weight_g)                                                            AS n_weighed,
    count(*) FILTER (WHERE judgement = 'OK')                                   AS n_ok,
    count(*) FILTER (WHERE judgement = 'HH')                                   AS n_hh,
    count(*) FILTER (WHERE judgement = 'HI')                                   AS n_hi,
    count(*) FILTER (WHERE judgement = 'LO')                                   AS n_lo,
    count(*) FILTER (WHERE judgement = 'LL')                                   AS n_ll,
    count(*) FILTER (WHERE judgement = 'TD')                                   AS n_td,
    count(*) FILTER (WHERE judgement = 'US')                                   AS n_us,
    count(*) FILTER (WHERE judgement = 'MD')                                   AS n_md,
    count(*) FILTER (WHERE judgement IN ('E1', 'E2'))                          AS n_ext,
    sum(weight_g)                                                              AS sum_w,
    sum(weight_g * weight_g)                                                   AS sum_w2,
    min(weight_g)                                                              AS min_w,
    max(weight_g)                                                              AS max_w,
    count(weight_g - target_g)                                                 AS n_dev,
    sum(weight_g - target_g)                                                   AS sum_dev,
    sum((weight_g - target_g) * (weight_g - target_g))                         AS sum_dev2,
    sum(target_g) FILTER (WHERE weight_g IS NOT NULL)                          AS sum_target,
    sum(weight_g) FILTER (WHERE judgement = 'OK')                              AS sum_w_ok,
    count(weight_g - target_g) FILTER (WHERE judgement = 'OK')                 AS n_dev_ok,
    sum(weight_g - target_g) FILTER (WHERE judgement = 'OK')                   AS sum_dev_ok,
    sum(target_g) FILTER (WHERE judgement = 'OK' AND weight_g IS NOT NULL)     AS sum_target_ok
FROM weighing
GROUP BY bucket, machine_id, product_id, shift_date, shift_code
WITH NO DATA;

SELECT add_continuous_aggregate_policy('weighing_15m',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '5 minutes');

-- Exact weight distribution (weights are quantised to the scale division), used for
-- median, mode and histograms over any range without scanning raw rows.
CREATE MATERIALIZED VIEW weighing_hist
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    time_bucket(INTERVAL '1 day', ts) AS bucket,
    machine_id,
    product_id,
    shift_date,
    shift_code,
    weight_g,
    count(*) AS n
FROM weighing
WHERE weight_g IS NOT NULL
GROUP BY bucket, machine_id, product_id, shift_date, shift_code, weight_g
WITH NO DATA;

SELECT add_continuous_aggregate_policy('weighing_hist',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes');
