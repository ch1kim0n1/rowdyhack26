-- The Appraisal Job: Tiger Cloud (TimescaleDB) event ledger.
--
-- Idempotent bootstrap. Run once against a WRITABLE service:
--     python -m rig.timescale bootstrap
-- It is safe to re-run; every statement guards with IF NOT EXISTS.

-- One row per recognition, from either device. Append-only event stream.
CREATE TABLE IF NOT EXISTS detections (
    ts            timestamptz      NOT NULL DEFAULT now(),
    case_no       integer          NOT NULL,
    device        text             NOT NULL,              -- 'hat' | 'rover'
    n             integer,                                -- exhibit number in the case
    item          text             NOT NULL,
    category      text             NOT NULL DEFAULT '',
    value_usd     double precision NOT NULL DEFAULT 0,
    estimated     boolean          NOT NULL DEFAULT true,
    source        text             NOT NULL DEFAULT 'unknown',   -- openai | anthropic | vultr | offline
    price_source  text             NOT NULL DEFAULT 'unknown',   -- serpapi | model_quote | vision | credential | exit
    weight_lb     double precision,
    mode          text             NOT NULL DEFAULT 'appraisal',
    hot           boolean          NOT NULL DEFAULT false        -- entered the top-5 at insert time
);

-- The hypertable: this is what keeps appends and time-window reads fast as the
-- stream grows across many walks and three devices.
SELECT create_hypertable('detections', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS detections_case_idx ON detections (case_no, ts DESC);
CREATE INDEX IF NOT EXISTS detections_value_idx ON detections (value_usd DESC, ts DESC);

-- Continuous aggregate: precomputed take / finds / top value per 5-minute
-- bucket, per case and device. "Value over time" and leaderboards read from
-- this instead of re-summing the raw rows on every request.
CREATE MATERIALIZED VIEW IF NOT EXISTS detections_5m
    WITH (timescaledb.continuous) AS
SELECT time_bucket('5 minutes', ts) AS bucket,
       case_no,
       device,
       count(*)        AS finds,
       sum(value_usd)  AS take,
       max(value_usd)  AS top_value
FROM detections
GROUP BY bucket, case_no, device
WITH NO DATA;

SELECT add_continuous_aggregate_policy('detections_5m',
    start_offset      => INTERVAL '1 hour',
    end_offset        => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists     => TRUE);

-- Hypercore columnar compression for cases older than a week.
ALTER TABLE detections SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'case_no, device',
    timescaledb.compress_orderby   = 'ts DESC'
);

SELECT add_compression_policy('detections', INTERVAL '7 days', if_not_exists => TRUE);

-- NOTIFY on every insert: the push backbone. A second hub (or a cloud
-- dashboard) LISTENs on 'detections' and reacts in real time without polling.
CREATE OR REPLACE FUNCTION detections_notify() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('detections', json_build_object(
        'case_no',   NEW.case_no,
        'device',    NEW.device,
        'item',      NEW.item,
        'value_usd', NEW.value_usd,
        'hot',       NEW.hot
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS detections_notify_trg ON detections;
CREATE TRIGGER detections_notify_trg
    AFTER INSERT ON detections
    FOR EACH ROW EXECUTE FUNCTION detections_notify();
