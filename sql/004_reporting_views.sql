DROP VIEW IF EXISTS reporting.product_performance, reporting.customer_summary,
    reporting.order_lines, reporting.orders, reporting.data_health,
    reporting.load_batches, reporting.rejection_reasons CASCADE;

CREATE VIEW reporting.orders AS
WITH base AS (
    SELECT
        o.order_id,
        o.order_number,
        o.data_source,
        o.customer_id,
        o.channel,
        o.country_code,
        o.status,
        o.currency,
        o.ordered_at,
        (o.ordered_at AT TIME ZONE 'Asia/Tokyo')::date AS order_date,
        date_trunc('month', o.ordered_at AT TIME ZONE 'Asia/Tokyo')::date AS order_month,
        o.amount_jpy,
        o.discount_jpy,
        o.shipping_jpy,
        o.tax_jpy,
        o.refund_jpy,
        (o.status IN ('paid', 'fulfilled')) AS is_counted
    FROM core.orders o
),
with_first AS (
    SELECT
        b.*,
        MIN(b.order_month) FILTER (WHERE b.is_counted)
            OVER (PARTITION BY b.customer_id) AS first_counted_month
    FROM base b
)
SELECT
    w.*,
    CASE WHEN w.is_counted
         THEN w.amount_jpy - LEAST(w.refund_jpy, w.amount_jpy)
         ELSE 0 END AS net_revenue_jpy,
    CASE
        WHEN NOT w.is_counted THEN NULL
        WHEN w.customer_id IS NULL THEN 'guest'
        WHEN w.first_counted_month = w.order_month THEN 'new'
        ELSE 'returning'
    END AS customer_type
FROM with_first w;

CREATE VIEW reporting.order_lines AS
SELECT
    i.order_item_id,
    o.order_id,
    o.order_number,
    o.data_source,
    o.order_date,
    o.order_month,
    o.channel,
    o.country_code,
    o.status,
    o.is_counted,
    o.customer_type,
    p.product_id,
    p.sku,
    p.name AS product_name,
    p.maker,
    p.category,
    i.quantity,
    i.unit_price_jpy,
    i.line_total_jpy,
    CASE WHEN o.is_counted AND SUM(i.line_total_jpy) OVER (PARTITION BY i.order_id) > 0
         THEN o.net_revenue_jpy::numeric * i.line_total_jpy
              / SUM(i.line_total_jpy) OVER (PARTITION BY i.order_id)
         ELSE 0 END AS net_revenue_jpy,
    CASE WHEN o.is_counted THEN i.quantity ELSE 0 END AS units_sold
FROM core.order_items i
JOIN reporting.orders o ON o.order_id = i.order_id
JOIN core.products p ON p.product_id = i.product_id;

CREATE VIEW reporting.customer_summary AS
SELECT
    c.customer_id,
    c.data_source,
    c.country_code,
    c.created_at,
    COUNT(o.order_id) FILTER (WHERE o.is_counted) AS counted_orders,
    COALESCE(SUM(o.net_revenue_jpy), 0) AS lifetime_revenue_jpy,
    MIN(o.order_date) FILTER (WHERE o.is_counted) AS first_order_date,
    MAX(o.order_date) FILTER (WHERE o.is_counted) AS last_order_date,
    (COUNT(o.order_id) FILTER (WHERE o.is_counted) >= 2) AS is_repeat_customer,
    CASE
        WHEN COUNT(o.order_id) FILTER (WHERE o.is_counted) = 0 THEN 'no counted orders'
        WHEN COUNT(o.order_id) FILTER (WHERE o.is_counted) = 1 THEN 'one-time'
        ELSE 'repeat'
    END AS segment
FROM core.customers c
LEFT JOIN reporting.orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.data_source, c.country_code, c.created_at;

CREATE VIEW reporting.product_performance AS
WITH as_of AS (
    SELECT MAX(order_date) AS as_of_date FROM reporting.orders WHERE is_counted
),
sales AS (
    SELECT
        l.product_id,
        SUM(l.units_sold) AS units_sold,
        SUM(l.net_revenue_jpy) AS net_revenue_jpy,
        MAX(l.order_date) FILTER (WHERE l.is_counted) AS last_sale_date,
        SUM(l.units_sold) FILTER (WHERE l.order_date > a.as_of_date - 30) AS units_last_30d
    FROM reporting.order_lines l
    CROSS JOIN as_of a
    GROUP BY l.product_id
),
latest_stock AS (
    SELECT DISTINCT ON (s.product_id)
        s.product_id, s.quantity_on_hand, s.snapshot_date
    FROM core.inventory_snapshots s
    ORDER BY s.product_id, s.snapshot_date DESC, s.data_source
),
combined AS (
    SELECT
        p.product_id,
        p.sku,
        p.name AS product_name,
        p.maker,
        p.category,
        p.price_jpy,
        p.product_url,
        COALESCE(s.units_sold, 0) AS units_sold,
        COALESCE(s.net_revenue_jpy, 0) AS net_revenue_jpy,
        s.last_sale_date,
        COALESCE(s.units_last_30d, 0) AS units_last_30d,
        st.quantity_on_hand AS stock_on_hand,
        st.snapshot_date AS stock_date,
        CASE WHEN COALESCE(s.units_last_30d, 0) > 0
             THEN ROUND(st.quantity_on_hand / (s.units_last_30d / 30.0), 1) END AS days_of_cover,
        a.as_of_date
    FROM core.products p
    CROSS JOIN as_of a
    LEFT JOIN sales s ON s.product_id = p.product_id
    LEFT JOIN latest_stock st ON st.product_id = p.product_id
)
SELECT
    c.*,
    (c.stock_on_hand IS NOT NULL
        AND (c.stock_on_hand <= 3 OR COALESCE(c.days_of_cover < 14, FALSE))) AS is_low_stock,
    (COALESCE(c.stock_on_hand, 0) > 0
        AND (c.last_sale_date IS NULL OR c.last_sale_date <= c.as_of_date - 60)) AS is_slow_mover
FROM combined c;

CREATE VIEW reporting.data_health AS
SELECT 'orders' AS item, data_source, COUNT(*) AS row_count, MAX(ordered_at) AS latest_at
FROM core.orders GROUP BY data_source
UNION ALL
SELECT 'customers', data_source, COUNT(*), MAX(created_at)
FROM core.customers GROUP BY data_source
UNION ALL
SELECT 'inventory snapshots', data_source, COUNT(*), MAX(snapshot_date)::timestamptz
FROM core.inventory_snapshots GROUP BY data_source
UNION ALL
SELECT 'products', 'catalog', COUNT(*), NULL::timestamptz
FROM core.products;

CREATE VIEW reporting.load_batches AS
SELECT batch_id, source_name, file_name, data_source, started_at, finished_at,
       status, rows_read, rows_loaded, rows_rejected
FROM staging.etl_batches;

CREATE VIEW reporting.rejection_reasons AS
SELECT b.source_name, r.entity, r.reason, COUNT(*) AS rejected_rows
FROM staging.rejected_rows r
JOIN staging.etl_batches b ON b.batch_id = r.batch_id
GROUP BY b.source_name, r.entity, r.reason;