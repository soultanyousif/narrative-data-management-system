ALTER TABLE core.inventory_snapshots
    ADD COLUMN IF NOT EXISTS data_source TEXT NOT NULL DEFAULT 'synthetic'
    CHECK (data_source IN ('synthetic', 'offline_csv', 'shopify_csv'));

ALTER TABLE core.inventory_snapshots
    DROP CONSTRAINT IF EXISTS inventory_snapshots_product_id_snapshot_date_key;

ALTER TABLE core.inventory_snapshots
    DROP CONSTRAINT IF EXISTS inventory_snapshots_source_product_date_key;

ALTER TABLE core.inventory_snapshots
    ADD CONSTRAINT inventory_snapshots_source_product_date_key
    UNIQUE (data_source, product_id, snapshot_date);