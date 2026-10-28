import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db import get_engine
from shopify_loader import (
    DELETE_ITEMS,
    EMAIL_PATTERN,
    INSERT_ITEM,
    finish_batch,
    first_nonblank,
    print_summary,
    rejection,
    save_rejected,
    start_batch,
)

REQUIRED = ["receipt_number", "sale_date", "sku", "quantity", "unit_price_jpy", "customer_email"]
EARLIEST_DATE = pd.Timestamp("2015-01-01", tz="Asia/Tokyo")

GET_OR_CREATE_CUSTOMER = text(
    """
    INSERT INTO core.customers (email, country_code, created_at, data_source)
    VALUES (:email, 'JP', :created_at, 'offline_csv')
    ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
    RETURNING customer_id
    """
)

UPSERT_ORDER = text(
    """
    INSERT INTO core.orders
        (order_number, data_source, customer_id, channel, country_code, status,
         currency, fx_rate_to_jpy, amount_original, amount_jpy, ordered_at,
         source, payment_status, fulfillment_status)
    VALUES
        (:order_number, 'offline_csv', :customer_id, 'offline', 'JP', 'fulfilled',
         'JPY', 1, :amount_jpy, :amount_jpy, :ordered_at,
         'register_excel', 'paid', 'fulfilled')
    ON CONFLICT (data_source, order_number) DO UPDATE SET
        customer_id = EXCLUDED.customer_id,
        amount_original = EXCLUDED.amount_original,
        amount_jpy = EXCLUDED.amount_jpy,
        ordered_at = EXCLUDED.ordered_at
    RETURNING order_id
    """
)


def read_sheet(path):
    df = pd.read_excel(path, sheet_name="Sales", dtype=str, keep_default_na=False)
    missing = [name for name in REQUIRED if name not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")
    df = df[REQUIRED].copy()
    df["row_number"] = range(2, len(df) + 2)
    for column in REQUIRED:
        df[column] = df[column].astype(str).str.strip()
    df["receipt_number"] = df["receipt_number"].str.replace(r"\.0$", "", regex=True)
    blank = (df[REQUIRED] == "").all(axis=1)
    return df[~blank]


def parse_quantity(value):
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        raise ValueError("quantity is not a number")
    if number <= 0 or not number.is_integer():
        raise ValueError("quantity must be a whole number above zero")
    return int(number)


def parse_price(value, default):
    if value == "":
        return int(default)
    try:
        price = round(float(value.replace(",", "")))
    except ValueError:
        raise ValueError("unit price is not a number")
    if price < 0:
        raise ValueError("unit price is negative")
    return price


def build_receipt(receipt, group, products):
    if receipt == "":
        raise ValueError("receipt number is missing")

    sale_date = pd.to_datetime(first_nonblank(group["sale_date"]), errors="coerce")
    if pd.isna(sale_date):
        raise ValueError("sale date is missing or invalid")
    if sale_date.tzinfo is not None:
        sale_date = sale_date.tz_localize(None)
    ordered_at = sale_date.normalize().tz_localize("Asia/Tokyo") + pd.Timedelta(hours=12)
    if ordered_at > pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1):
        raise ValueError("sale date is in the future")
    if ordered_at < EARLIEST_DATE:
        raise ValueError("sale date is before 2015")

    email = first_nonblank(group["customer_email"]).lower()
    if email and not EMAIL_PATTERN.match(email):
        raise ValueError("customer email is invalid")

    items = {}
    for row in group.itertuples():
        product = products.get(row.sku)
        if product is None:
            raise ValueError(f"SKU {row.sku!r} is not in the catalog")
        quantity = parse_quantity(row.quantity)
        price = parse_price(row.unit_price_jpy, product["price_jpy"])
        if row.sku in items:
            if items[row.sku]["unit_price_jpy"] != price:
                raise ValueError(f"{row.sku} appears twice with different prices")
            items[row.sku]["quantity"] += quantity
        else:
            items[row.sku] = {
                "product_id": product["product_id"],
                "quantity": quantity,
                "unit_price_jpy": price,
            }

    item_list = list(items.values())
    return {
        "order_number": receipt,
        "email": email or None,
        "ordered_at": ordered_at.to_pydatetime(),
        "amount_jpy": sum(item["quantity"] * item["unit_price_jpy"] for item in item_list),
        "items": item_list,
    }


def load_offline(engine, path):
    df = read_sheet(path)
    batch_id = start_batch(engine, path.name, "offline_sales", "offline_csv")
    records_read = df["receipt_number"].nunique()
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT sku, product_id, price_jpy FROM core.products")).all()
        products = {r.sku: {"product_id": r.product_id, "price_jpy": r.price_jpy} for r in rows}

        good, rejected = [], []
        for receipt, group in df.groupby("receipt_number", sort=False):
            row_number = int(group["row_number"].iloc[0])
            try:
                good.append(build_receipt(receipt, group, products))
            except ValueError as error:
                payload = {"receipt_number": receipt}
                rejected.append(rejection("offline_receipts", row_number, str(error), payload))
        good.sort(key=lambda order: order["ordered_at"])

        with engine.begin() as connection:
            for order in good:
                customer_id = None
                if order["email"]:
                    customer_id = connection.execute(
                        GET_OR_CREATE_CUSTOMER,
                        {"email": order["email"], "created_at": order["ordered_at"]},
                    ).scalar()
                order_id = connection.execute(
                    UPSERT_ORDER,
                    {
                        "order_number": order["order_number"],
                        "customer_id": customer_id,
                        "amount_jpy": order["amount_jpy"],
                        "ordered_at": order["ordered_at"],
                    },
                ).scalar()
                connection.execute(DELETE_ITEMS, {"order_id": order_id})
                connection.execute(
                    INSERT_ITEM, [{**item, "order_id": order_id} for item in order["items"]]
                )
            save_rejected(connection, batch_id, rejected)
        finish_batch(engine, batch_id, "succeeded", records_read, len(good), len(rejected))
    except Exception:
        finish_batch(engine, batch_id, "failed", records_read, 0, 0)
        raise
    print_summary("offline receipts", records_read, len(good), rejected)


def main():
    parser = argparse.ArgumentParser(description="Load an offline sales Excel file")
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    engine = get_engine()
    print("database:", engine.url.database)
    if "fixtures" in str(args.file).lower() and not engine.url.database.endswith("_test"):
        parser.error(f"{args.file} is a test fixture and may only be loaded into a *_test database")
    load_offline(engine, args.file)


if __name__ == "__main__":
    main()