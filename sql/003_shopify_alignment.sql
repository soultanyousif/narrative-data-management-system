ALTER TABLE core.customers
    ADD COLUMN IF NOT EXISTS shopify_customer_id TEXT,
    ADD COLUMN IF NOT EXISTS language TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_shopify_id
    ON core.customers (shopify_customer_id)
    WHERE shopify_customer_id IS NOT NULL;

ALTER TABLE core.orders
    ADD COLUMN IF NOT EXISTS shopify_order_id TEXT,
    ADD COLUMN IF NOT EXISTS source TEXT,
    ADD COLUMN IF NOT EXISTS payment_status TEXT,
    ADD COLUMN IF NOT EXISTS fulfillment_status TEXT,
    ADD COLUMN IF NOT EXISTS tax_jpy BIGINT NOT NULL DEFAULT 0 CHECK (tax_jpy >= 0),
    ADD COLUMN IF NOT EXISTS shipping_jpy BIGINT NOT NULL DEFAULT 0 CHECK (shipping_jpy >= 0),
    ADD COLUMN IF NOT EXISTS discount_jpy BIGINT NOT NULL DEFAULT 0 CHECK (discount_jpy >= 0),
    ADD COLUMN IF NOT EXISTS refund_jpy BIGINT NOT NULL DEFAULT 0 CHECK (refund_jpy >= 0);

COMMENT ON COLUMN core.orders.amount_jpy IS 'Items total in JPY, tax included, shipping excluded';
COMMENT ON COLUMN core.orders.tax_jpy IS 'Tax already included in amount_jpy';
COMMENT ON COLUMN core.orders.shipping_jpy IS 'Shipping charged, not part of amount_jpy';
COMMENT ON COLUMN core.orders.refund_jpy IS 'Refunded amount; full or partial';

CREATE TABLE IF NOT EXISTS staging.etl_batches (
    batch_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name    TEXT NOT NULL,
    file_name      TEXT NOT NULL,
    data_source    TEXT NOT NULL CHECK (data_source IN ('synthetic', 'offline_csv', 'shopify_csv')),
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    rows_read      INTEGER,
    rows_loaded    INTEGER,
    rows_rejected  INTEGER,
    status         TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed'))
);

CREATE TABLE IF NOT EXISTS staging.raw_rows (
    raw_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id    BIGINT NOT NULL REFERENCES staging.etl_batches (batch_id) ON DELETE CASCADE,
    entity      TEXT NOT NULL,
    row_number  INTEGER NOT NULL,
    payload     JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.rejected_rows (
    rejected_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id     BIGINT NOT NULL REFERENCES staging.etl_batches (batch_id) ON DELETE CASCADE,
    entity       TEXT NOT NULL,
    row_number   INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    payload      JSONB
);

CREATE INDEX IF NOT EXISTS idx_raw_rows_batch ON staging.raw_rows (batch_id);
CREATE INDEX IF NOT EXISTS idx_rejected_batch ON staging.rejected_rows (batch_id);