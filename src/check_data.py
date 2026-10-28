import sys

import pandas as pd
from sqlalchemy import text

from db import get_engine

SEED_PRODUCTS = len(pd.read_csv("data/seed/products.csv"))

CHECKS = [
    (
        "all catalog products are in the database",
        "SELECT COUNT(*) FROM core.products",
        SEED_PRODUCTS,
    ),
    (
        "products without any stock record (when stock data exists)",
        """SELECT CASE WHEN EXISTS (SELECT 1 FROM core.inventory_snapshots)
           THEN (SELECT COUNT(*) FROM core.products p
                 WHERE NOT EXISTS (SELECT 1 FROM core.inventory_snapshots s
                                   WHERE s.product_id = p.product_id))
           ELSE 0 END""",
        0,
    ),
    (
        "orders without any item",
        """SELECT COUNT(*) FROM core.orders o
           WHERE NOT EXISTS (SELECT 1 FROM core.order_items i
                             WHERE i.order_id = o.order_id)""",
        0,
    ),
    (
        "orders whose total differs from item lines minus discount",
        """SELECT COUNT(*) FROM core.orders o
           JOIN (SELECT order_id, SUM(line_total_jpy) AS lines_total
                 FROM core.order_items GROUP BY order_id) t USING (order_id)
           WHERE o.amount_jpy <> t.lines_total - o.discount_jpy""",
        0,
    ),
    (
        "orders where original amount x rate differs from JPY by more than 2 yen",
        """SELECT COUNT(*) FROM core.orders
           WHERE ABS(amount_original * fx_rate_to_jpy - amount_jpy) > 2""",
        0,
    ),
    (
        "refunds larger than the order including shipping",
        "SELECT COUNT(*) FROM core.orders WHERE refund_jpy > amount_jpy + shipping_jpy",
        0,
    ),
    (
        "Shopify order IDs that appear more than once",
        """SELECT COUNT(*) FROM (
               SELECT shopify_order_id FROM core.orders
               WHERE shopify_order_id IS NOT NULL
               GROUP BY shopify_order_id HAVING COUNT(*) > 1) d""",
        0,
    ),
    (
        "offline orders that are not Japan or JPY",
        """SELECT COUNT(*) FROM core.orders
           WHERE channel = 'offline' AND (country_code <> 'JP' OR currency <> 'JPY')""",
        0,
    ),
    (
        "load batches that failed",
        "SELECT COUNT(*) FROM staging.etl_batches WHERE status = 'failed'",
        0,
    ),
    (
        "online orders without a customer (synthetic only)",
        """SELECT COUNT(*) FROM core.orders
           WHERE data_source = 'synthetic' AND channel = 'online' AND customer_id IS NULL""",
        0,
    ),
    (
        "customers with no orders (synthetic only)",
        """SELECT COUNT(*) FROM core.customers c
           WHERE c.data_source = 'synthetic'
             AND NOT EXISTS (SELECT 1 FROM core.orders o WHERE o.customer_id = c.customer_id)""",
        0,
    ),
    (
        "orders dated outside the 12-month period (synthetic only)",
        """SELECT COUNT(*) FROM core.orders
           WHERE data_source = 'synthetic'
             AND (ordered_at < '2025-10-27 00:00:00+00' OR ordered_at >= '2026-10-26 00:00:00+00')""",
        0,
    ),
    (
        "order lines priced differently from the catalog (synthetic only)",
        """SELECT COUNT(*) FROM core.order_items i
           JOIN core.orders o USING (order_id)
           JOIN core.products p USING (product_id)
           WHERE o.data_source = 'synthetic' AND i.unit_price_jpy <> p.price_jpy""",
        0,
    ),
]

INFO = [
    ("orders", "SELECT COUNT(*) FROM core.orders"),
    ("customers", "SELECT COUNT(*) FROM core.customers"),
    (
        "revenue counted (paid and fulfilled, net of refunds), JPY",
        """SELECT SUM(amount_jpy - LEAST(refund_jpy, amount_jpy)) FROM core.orders
           WHERE status IN ('paid', 'fulfilled')""",
    ),
    (
        "revenue if cancelled and refunded were wrongly included, JPY",
        "SELECT SUM(amount_jpy) FROM core.orders",
    ),
    (
        "products with 3 or fewer units in the latest snapshot",
        """SELECT COUNT(*) FROM core.inventory_snapshots s
           WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM core.inventory_snapshots)
             AND s.quantity_on_hand <= 3""",
    ),
]


def main():
    engine = get_engine()
    print("database:", engine.url.database)
    failures = 0
    with engine.connect() as connection:
        for name, sql, expected in CHECKS:
            value = connection.execute(text(sql)).scalar()
            passed = value == expected
            failures += 0 if passed else 1
            print(f"{'PASS' if passed else 'FAIL'} | {name} | got {value}, expected {expected}")
        print()
        for name, sql in INFO:
            print(f"info | {name}: {connection.execute(text(sql)).scalar()}")
    print()
    print("all checks passed" if failures == 0 else f"{failures} check(s) FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()