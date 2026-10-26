CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS reporting;

CREATE TABLE IF NOT EXISTS core.customers (
    customer_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT UNIQUE,
    first_name    TEXT,
    last_name     TEXT,
    country_code  CHAR(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    created_at    TIMESTAMPTZ NOT NULL,
    data_source   TEXT NOT NULL CHECK (data_source IN ('synthetic', 'offline_csv', 'shopify_csv'))
);

CREATE TABLE IF NOT EXISTS core.products (
    product_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku          TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    maker        TEXT NOT NULL,
    category     TEXT NOT NULL CHECK (category IN (
                     'Tableware & Dining',
                     'Interior & Home Decor',
                     'Bags & Accessories',
                     'Jewelry',
                     'Lifestyle Goods & Miscellaneous')),
    price_jpy    INTEGER NOT NULL CHECK (price_jpy > 0),
    product_url  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS core.orders (
    order_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number     TEXT NOT NULL,
    data_source      TEXT NOT NULL CHECK (data_source IN ('synthetic', 'offline_csv', 'shopify_csv')),
    customer_id      BIGINT REFERENCES core.customers (customer_id),
    channel          TEXT NOT NULL CHECK (channel IN ('online', 'offline')),
    country_code     CHAR(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    status           TEXT NOT NULL CHECK (status IN ('paid', 'fulfilled', 'cancelled', 'refunded')),
    currency         CHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    fx_rate_to_jpy   NUMERIC(14, 6) NOT NULL CHECK (fx_rate_to_jpy > 0),
    amount_original  NUMERIC(14, 2) NOT NULL CHECK (amount_original >= 0),
    amount_jpy       BIGINT NOT NULL CHECK (amount_jpy >= 0),
    ordered_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (data_source, order_number)
);

CREATE TABLE IF NOT EXISTS core.order_items (
    order_item_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id         BIGINT NOT NULL REFERENCES core.orders (order_id) ON DELETE CASCADE,
    product_id       BIGINT NOT NULL REFERENCES core.products (product_id),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_jpy   INTEGER NOT NULL CHECK (unit_price_jpy >= 0),
    line_total_jpy   BIGINT GENERATED ALWAYS AS (quantity * unit_price_jpy) STORED,
    UNIQUE (order_id, product_id)
);

CREATE TABLE IF NOT EXISTS core.inventory_snapshots (
    snapshot_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id       BIGINT NOT NULL REFERENCES core.products (product_id),
    snapshot_date    DATE NOT NULL,
    quantity_on_hand INTEGER NOT NULL CHECK (quantity_on_hand >= 0),
    UNIQUE (product_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_orders_ordered_at ON core.orders (ordered_at);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON core.orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_country ON core.orders (country_code);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON core.order_items (product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_date ON core.inventory_snapshots (snapshot_date);