from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db import get_engine

DATA_DIR = Path("data/generated")

UPSERT_CUSTOMERS = text(
    """
    INSERT INTO core.customers
        (email, first_name, last_name, country_code, created_at, data_source)
    VALUES
        (:email, :first_name, :last_name, :country_code, :created_at, :data_source)
    ON CONFLICT (email) DO UPDATE SET
        first_name = EXCLUDED.first_name,
        last_name = EXCLUDED.last_name,
        country_code = EXCLUDED.country_code,
        created_at = EXCLUDED.created_at,
        data_source = EXCLUDED.data_source
    """
)

UPSERT_ORDERS = text(
    """
    INSERT INTO core.orders
        (order_number, data_source, customer_id, channel, country_code, status,
         currency, fx_rate_to_jpy, amount_original, amount_jpy, ordered_at)
    VALUES
        (:order_number, :data_source, :customer_id, :channel, :country_code, :status,
         :currency, :fx_rate_to_jpy, :amount_original, :amount_jpy, :ordered_at)
    ON CONFLICT (data_source, order_number) DO UPDATE SET
        customer_id = EXCLUDED.customer_id,
        channel = EXCLUDED.channel,
        country_code = EXCLUDED.country_code,
        status = EXCLUDED.status,
        currency = EXCLUDED.currency,
        fx_rate_to_jpy = EXCLUDED.fx_rate_to_jpy,
        amount_original = EXCLUDED.amount_original,
        amount_jpy = EXCLUDED.amount_jpy,
        ordered_at = EXCLUDED.ordered_at
    """
)

UPSERT_ITEMS = text(
    """
    INSERT INTO core.order_items (order_id, product_id, quantity, unit_price_jpy)
    VALUES (:order_id, :product_id, :quantity, :unit_price_jpy)
    ON CONFLICT (order_id, product_id) DO UPDATE SET
        quantity = EXCLUDED.quantity,
        unit_price_jpy = EXCLUDED.unit_price_jpy
    """
)

UPSERT_INVENTORY = text(
    """
    INSERT INTO core.inventory_snapshots
        (product_id, snapshot_date, quantity_on_hand, data_source)
    VALUES (:product_id, :snapshot_date, :quantity_on_hand, :data_source)
    ON CONFLICT (data_source, product_id, snapshot_date) DO UPDATE SET
        quantity_on_hand = EXCLUDED.quantity_on_hand
    """
)


def to_records(df):
    cleaned = df.astype(object).where(df.notna(), None)
    return cleaned.to_dict("records")


def require_all_matched(df, column, name):
    missing = df[column].isna().sum()
    if missing:
        raise ValueError(f"{missing} rows in {name} could not be matched on {column}")


def main():
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    orders = pd.read_csv(DATA_DIR / "orders.csv")
    items = pd.read_csv(DATA_DIR / "order_items.csv")
    inventory = pd.read_csv(DATA_DIR / "inventory_snapshots.csv")

    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(UPSERT_CUSTOMERS, to_records(customers))

        customer_ids = pd.read_sql(
            text("SELECT email AS customer_email, customer_id FROM core.customers"), connection
        )
        orders = orders.merge(customer_ids, on="customer_email", how="left")
        has_email = orders["customer_email"].notna()
        require_all_matched(orders[has_email], "customer_id", "orders")
        orders["customer_id"] = orders["customer_id"].astype("Int64")
        order_columns = [
            "order_number", "data_source", "customer_id", "channel", "country_code",
            "status", "currency", "fx_rate_to_jpy", "amount_original", "amount_jpy",
            "ordered_at",
        ]
        connection.execute(UPSERT_ORDERS, to_records(orders[order_columns]))

        order_ids = pd.read_sql(
            text("SELECT order_number, order_id FROM core.orders WHERE data_source = 'synthetic'"),
            connection,
        )
        product_ids = pd.read_sql(text("SELECT sku, product_id FROM core.products"), connection)

        items = items.merge(order_ids, on="order_number", how="left")
        items = items.merge(product_ids, on="sku", how="left")
        require_all_matched(items, "order_id", "order_items")
        require_all_matched(items, "product_id", "order_items")
        item_columns = ["order_id", "product_id", "quantity", "unit_price_jpy"]
        connection.execute(UPSERT_ITEMS, to_records(items[item_columns]))

        inventory = inventory.merge(product_ids, on="sku", how="left")
        require_all_matched(inventory, "product_id", "inventory_snapshots")
        inventory_columns = ["product_id", "snapshot_date", "quantity_on_hand", "data_source"]
        connection.execute(UPSERT_INVENTORY, to_records(inventory[inventory_columns]))

        for table in ["customers", "products", "orders", "order_items", "inventory_snapshots"]:
            count = connection.execute(text(f"SELECT COUNT(*) FROM core.{table}")).scalar()
            print(f"{table}: {count}")


if __name__ == "__main__":
    main()