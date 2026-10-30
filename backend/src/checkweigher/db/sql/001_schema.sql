-- Core schema. Works on plain PostgreSQL >= 15; 002 turns `weighing` into a hypertable when available.

CREATE TABLE machine (
    id          smallint PRIMARY KEY,
    code        text        NOT NULL UNIQUE,
    name        text        NOT NULL,
    mode        text        NOT NULL,
    active      boolean     NOT NULL DEFAULT true,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Shifts that cross midnight (start > end) belong to the production date they started on.
CREATE TABLE shift (
    code        text PRIMARY KEY,
    name        text     NOT NULL,
    start_time  time     NOT NULL,
    end_time    time     NOT NULL,
    sort        smallint NOT NULL DEFAULT 0
);

INSERT INTO shift (code, name, start_time, end_time, sort) VALUES
    ('A', 'Shift A', '06:00', '14:00', 1),
    ('B', 'Shift B', '14:00', '22:00', 2),
    ('C', 'Shift C', '22:00', '06:00', 3);

-- One row per distinct set of product settings seen on a machine (read via Modbus).
-- Weighings reference the settings that were active when they were judged.
CREATE TABLE product_setting (
    id            serial PRIMARY KEY,
    machine_id    smallint      NOT NULL REFERENCES machine (id),
    group_no      smallint      NOT NULL,
    product_no    smallint      NOT NULL,
    target_g      numeric(12,4),
    hihi_g        numeric(12,4),
    hi_g          numeric(12,4),
    lo_g          numeric(12,4),
    lolo_g        numeric(12,4),
    tare_g        numeric(12,4),
    ow_exception  boolean,
    reject_stage  smallint,
    first_seen    timestamptz   NOT NULL DEFAULT now(),
    last_seen     timestamptz   NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (machine_id, group_no, product_no, target_g, hihi_g, hi_g, lo_g, lolo_g,
                               tare_g, ow_exception, reject_stage)
);

-- One row per judged product.
CREATE TABLE weighing (
    ts          timestamptz   NOT NULL,           -- collector clock (NTP/RTC), UTC
    machine_id  smallint      NOT NULL,
    seq         integer,                          -- indicator running number; NULL for TD/US lines
    judgement   text          NOT NULL,           -- OK HH HI LO LL TD US MD E1 E2
    weight_g    numeric(12,4),                    -- NULL when no weight (TD/US, missed in modbus mode)
    target_g    numeric(12,4),                    -- denormalised from product_setting for aggregates
    product_id  integer,
    shift_date  date          NOT NULL,           -- production date
    shift_code  text          NOT NULL,
    source      text          NOT NULL,           -- serial | modbus | usb
    raw         text
);

CREATE UNIQUE INDEX weighing_machine_ts_uq ON weighing (machine_id, ts);
CREATE INDEX weighing_shift_idx ON weighing (shift_date, shift_code, machine_id);

-- Serial-vs-indicator-counter cross check, one row per reconcile window.
CREATE TABLE reconciliation (
    id            bigserial PRIMARY KEY,
    machine_id    smallint    NOT NULL,
    window_start  timestamptz NOT NULL,
    window_end    timestamptz NOT NULL,
    shift_date    date        NOT NULL,
    shift_code    text        NOT NULL,
    expected      integer     NOT NULL,   -- delta of the indicator's total counter
    received      integer     NOT NULL,   -- records the collector stored in the window
    detail        jsonb
);

CREATE INDEX reconciliation_shift_idx ON reconciliation (shift_date, shift_code, machine_id);

CREATE TABLE collector_event (
    id          bigserial PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),
    machine_id  smallint,
    kind        text        NOT NULL,
    message     text        NOT NULL,
    detail      jsonb
);

CREATE INDEX collector_event_ts_idx ON collector_event (ts DESC);

-- Live state written by the collector every few seconds.
CREATE TABLE machine_status (
    machine_id       smallint PRIMARY KEY,
    serial_state     text,
    modbus_state     text,
    last_line_at     timestamptz,
    last_modbus_at   timestamptz,
    last_ts          timestamptz,
    last_weight_g    numeric(12,4),
    last_judgement   text,
    last_seq         integer,
    product_id       integer,
    device_counters  jsonb,
    updated_at       timestamptz NOT NULL DEFAULT now()
);
