-- Plain PostgreSQL variant (development / tests): same columns as the TimescaleDB
-- continuous aggregates, computed on the fly by ordinary views.

CREATE VIEW weighing_15m AS
SELECT
    date_bin(INTERVAL '15 minutes', ts, TIMESTAMPTZ '2000-01-01 00:00:00+00') AS bucket,
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
GROUP BY 1, machine_id, product_id, shift_date, shift_code;

CREATE VIEW weighing_hist AS
SELECT
    date_bin(INTERVAL '1 day', ts, TIMESTAMPTZ '2000-01-01 00:00:00+00') AS bucket,
    machine_id,
    product_id,
    shift_date,
    shift_code,
    weight_g,
    count(*) AS n
FROM weighing
WHERE weight_g IS NOT NULL
GROUP BY 1, machine_id, product_id, shift_date, shift_code, weight_g;
