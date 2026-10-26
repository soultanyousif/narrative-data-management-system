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
        "products without any stock record",
        """SELECT COUNT(*) FROM core.products p
           WHERE NOT EXISTS (SELECT 1 FROM core.inventory_snapshots s
                             WHERE s.product_id = p.product_id)""",
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
        "orders whose total differs from the sum of their lines",
        """SELECT COUNT(*) FROM core.orders o
           JOIN (SELECT order_id, SUM(line_total_jpy) AS lines_total
                 FROM core.order_items GROUP BY order_id) t USING (order_id)
           WHERE o.amount_jpy <> t.lines_total""",
        0,
    ),
    (
        "orders where original amount x rate differs from JPY by more than 2 yen",
        """SELECT COUNT(*) FROM core.orders
           WHERE ABS(amount_original * fx_rate_to_jpy - amount_jpy) > 2""",
        0,
    ),
    (
        "online orders without a customer",
        "SELECT COUNT(*) FROM core.orders WHERE channel = 'online' AND customer_id IS NULL",
        0,
    ),
    (
        "offline orders that are not Japan or JPY",
        """SELECT COUNT(*) FROM core.orders
           WHERE channel = 'offline' AND (country_code <> 'JP' OR currency <> 'JPY')""",
        0,
    ),
    (
        "customers with no orders",
        """SELECT COUNT(*) FROM core.customers c
           WHERE NOT EXISTS (SELECT 1 FROM core.orders o
                             WHERE o.customer_id = c.customer_id)""",
        0,
    ),
    (
        "orders dated outside the 12-month period",
        """SELECT COUNT(*) FROM core.orders
           WHERE ordered_at < '2025-10-27 00:00:00+00'
              OR ordered_at >= '2026-10-26 00:00:00+00'""",
        0,
    ),
    (
        "order lines priced differently from the catalog (synthetic data only)",
        """SELECT COUNT(*) FROM core.order_items i
           JOIN core.products p USING (product_id)
           WHERE i.unit_price_jpy <> p.price_jpy""",
        0,
    ),
]

INFO = [
    ("orders", "SELECT COUNT(*) FROM core.orders"),
    ("customers", "SELECT COUNT(*) FROM core.customers"),
    (
        "revenue counted (paid and fulfilled), JPY",
        """SELECT SUM(amount_jpy) FROM core.orders
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