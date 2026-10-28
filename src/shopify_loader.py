import argparse
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml
from sqlalchemy import text

from db import get_engine

MAPPING_PATH = Path("config/shopify_mapping.yaml")
UNKNOWN_COUNTRY = "ZZ"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

UPDATE_CUSTOMER = text(
    """
    UPDATE core.customers
    SET email = :email, language = :language, country_code = :country_code
    WHERE shopify_customer_id = :shopify_customer_id
    """
)

INSERT_CUSTOMER = text(
    """
    INSERT INTO core.customers
        (shopify_customer_id, email, language, country_code, created_at, data_source)
    VALUES
        (:shopify_customer_id, :email, :language, :country_code, :created_at, 'shopify_csv')
    ON CONFLICT (email) DO UPDATE SET
        shopify_customer_id = COALESCE(core.customers.shopify_customer_id, EXCLUDED.shopify_customer_id),
        language = EXCLUDED.language
    """
)

UPSERT_ORDER = text(
    """
    INSERT INTO core.orders
        (order_number, data_source, customer_id, channel, country_code, status,
         currency, fx_rate_to_jpy, amount_original, amount_jpy, ordered_at,
         shopify_order_id, source, payment_status, fulfillment_status,
         tax_jpy, shipping_jpy, discount_jpy, refund_jpy)
    VALUES
        (:order_number, 'shopify_csv', :customer_id, :channel, :country_code, :status,
         :currency, :fx_rate_to_jpy, :amount_original, :amount_jpy, :ordered_at,
         :shopify_order_id, :source, :payment_status, :fulfillment_status,
         :tax_jpy, :shipping_jpy, :discount_jpy, :refund_jpy)
    ON CONFLICT (data_source, order_number) DO UPDATE SET
        customer_id = EXCLUDED.customer_id,
        channel = EXCLUDED.channel,
        country_code = EXCLUDED.country_code,
        status = EXCLUDED.status,
        currency = EXCLUDED.currency,
        fx_rate_to_jpy = EXCLUDED.fx_rate_to_jpy,
        amount_original = EXCLUDED.amount_original,
        amount_jpy = EXCLUDED.amount_jpy,
        ordered_at = EXCLUDED.ordered_at,
        shopify_order_id = EXCLUDED.shopify_order_id,
        source = EXCLUDED.source,
        payment_status = EXCLUDED.payment_status,
        fulfillment_status = EXCLUDED.fulfillment_status,
        tax_jpy = EXCLUDED.tax_jpy,
        shipping_jpy = EXCLUDED.shipping_jpy,
        discount_jpy = EXCLUDED.discount_jpy,
        refund_jpy = EXCLUDED.refund_jpy
    RETURNING order_id
    """
)

DELETE_ITEMS = text("DELETE FROM core.order_items WHERE order_id = :order_id")

INSERT_ITEM = text(
    """
    INSERT INTO core.order_items (order_id, product_id, quantity, unit_price_jpy)
    VALUES (:order_id, :product_id, :quantity, :unit_price_jpy)
    """
)


def load_mapping():
    with MAPPING_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_allowlisted(path, columns):
    wanted = set(columns.values())
    header = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns
    missing = wanted - set(header)
    if missing:
        raise ValueError(f"{path.name} is missing expected columns: {sorted(missing)}")
    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
        usecols=lambda name: name in wanted,
    )
    df = df.rename(columns={column: key for key, column in columns.items()})
    df["row_number"] = range(2, len(df) + 2)
    return df


def first_nonblank(series):
    for value in series:
        if value.strip() != "":
            return value.strip()
    return ""


def parse_money(value, field, required=False):
    cleaned = value.strip().replace(",", "")
    if cleaned == "":
        if required:
            raise ValueError(f"{field} is missing")
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        raise ValueError(f"{field} is not a number")


def parse_time(value, field):
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(stamp):
        raise ValueError(f"{field} is missing or not a valid date")
    return stamp.to_pydatetime()


def rejection(entity, row_number, reason, payload):
    return {"entity": entity, "row_number": row_number, "reason": reason, "payload": payload}


def pick_customer_country(group):
    defaults = group[group["address_is_default"].str.lower() == "true"]
    for source in (defaults, group):
        value = first_nonblank(source["address_country"]).upper()
        if re.fullmatch(r"[A-Z]{2}", value):
            return value
    return UNKNOWN_COUNTRY


def build_customers(df):
    good, rejected = [], []
    for shopify_id, group in df.groupby("shopify_customer_id", sort=False):
        row_number = int(group["row_number"].iloc[0])
        try:
            if shopify_id.strip() == "":
                raise ValueError("customer ID is blank")
            email = first_nonblank(group["email"]).lower()
            if not EMAIL_PATTERN.match(email):
                raise ValueError("email is missing or invalid")
            good.append(
                {
                    "shopify_customer_id": shopify_id.strip(),
                    "email": email,
                    "language": first_nonblank(group["language"]) or None,
                    "country_code": pick_customer_country(group),
                    "created_at": parse_time(first_nonblank(group["created_at"]), "Created At"),
                }
            )
        except ValueError as error:
            rejected.append(
                rejection("customers", row_number, str(error), {"shopify_customer_id": shopify_id})
            )
    return good, rejected


def pick_order_country(group):
    for column in ("shipping_country", "billing_country"):
        value = first_nonblank(group[column]).upper()
        if re.fullmatch(r"[A-Z]{2}", value):
            return value
    return UNKNOWN_COUNTRY


def build_items(lines, product_ids):
    merged = {}
    for row in lines.itertuples():
        handle = row.product_handle.strip()
        if handle == "":
            raise ValueError("a line item has no product handle")
        product_id = product_ids.get(handle)
        if product_id is None:
            raise ValueError(f"product handle {handle!r} is not in the catalog")
        quantity = int(parse_money(row.quantity, "Line: Quantity", required=True))
        price = round(parse_money(row.unit_price_jpy, "Line: Price (Shop Currency)", required=True))
        if quantity <= 0:
            raise ValueError("a line quantity is not above zero")
        if price < 0:
            raise ValueError("a line price is negative")
        if product_id in merged:
            if merged[product_id]["unit_price_jpy"] != price:
                raise ValueError(f"product {handle!r} appears twice with different prices")
            merged[product_id]["quantity"] += quantity
        else:
            merged[product_id] = {
                "product_id": product_id,
                "quantity": quantity,
                "unit_price_jpy": price,
            }
    return list(merged.values())


def build_one_order(shopify_id, group, mapping, product_ids, customer_ids):
    if shopify_id.strip() == "":
        raise ValueError("order ID is blank")
    order_number = first_nonblank(group["order_number"])
    if order_number == "":
        raise ValueError("order name is blank")

    source = first_nonblank(group["source"]).lower()
    channel = mapping["source_to_channel"].get(source)
    if channel is None:
        raise ValueError(f"source {source!r} is not supported yet")

    payment = first_nonblank(group["payment_status"]).lower()
    status = mapping["payment_status_map"].get(payment)
    if status is None:
        raise ValueError(f"payment status {payment!r} is not supported yet")
    fulfillment = first_nonblank(group["fulfillment_status"]).lower()

    currency = first_nonblank(group["currency"]).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency is missing or invalid")
    ordered_at = parse_time(first_nonblank(group["created_at"]), "Created At")

    subtotal_original = parse_money(
        first_nonblank(group["subtotal_original"]), "Price: Subtotal", required=True
    )
    subtotal_jpy = round(
        parse_money(
            first_nonblank(group["subtotal_jpy"]), "Price: Subtotal (Shop Currency)", required=True
        )
    )
    tax_jpy = round(parse_money(first_nonblank(group["tax_jpy"]), "Tax: Total"))
    shipping_jpy = round(parse_money(first_nonblank(group["shipping_jpy"]), "Total Shipping"))
    discount_jpy = round(parse_money(first_nonblank(group["discount_jpy"]), "Total Discount"))
    refund_jpy = round(parse_money(first_nonblank(group["refund_jpy"]), "Total Refund"))
    if min(subtotal_original, subtotal_jpy, tax_jpy, shipping_jpy, discount_jpy, refund_jpy) < 0:
        raise ValueError("an amount is negative")

    lines = group[group["line_type"] == mapping["line_item_type"]]
    if lines.empty:
        raise ValueError("order has no line items")
    items = build_items(lines, product_ids)
    lines_total = sum(item["quantity"] * item["unit_price_jpy"] for item in items)
    if abs(lines_total - (subtotal_jpy + discount_jpy)) > 1:
        raise ValueError(
            f"line items total {lines_total} does not match subtotal {subtotal_jpy}"
            f" plus discount {discount_jpy}"
        )

    shopify_customer = first_nonblank(group["customer_id"])
    customer_id = None
    if shopify_customer:
        customer_id = customer_ids.get(shopify_customer)
        if customer_id is None:
            raise ValueError("customer is not in the database; load the Customers export first")

    if first_nonblank(group["cancelled_at"]):
        status = "cancelled"
    elif status == "paid" and refund_jpy > 0 and refund_jpy >= subtotal_jpy + shipping_jpy:
        status = "refunded"
    elif status == "paid" and fulfillment == "fulfilled":
        status = "fulfilled"

    if currency == "JPY" or subtotal_original <= 0:
        fx_rate = 1.0
    else:
        fx_rate = round(subtotal_jpy / subtotal_original, 6)

    return {
        "order_number": order_number,
        "customer_id": customer_id,
        "channel": channel,
        "country_code": pick_order_country(group),
        "status": status,
        "currency": currency,
        "fx_rate_to_jpy": fx_rate,
        "amount_original": round(subtotal_original, 2),
        "amount_jpy": subtotal_jpy,
        "ordered_at": ordered_at,
        "shopify_order_id": shopify_id.strip(),
        "source": source,
        "payment_status": payment,
        "fulfillment_status": fulfillment,
        "tax_jpy": tax_jpy,
        "shipping_jpy": shipping_jpy,
        "discount_jpy": discount_jpy,
        "refund_jpy": refund_jpy,
        "items": items,
    }


def build_orders(df, mapping, product_ids, customer_ids):
    good, rejected = [], []
    for shopify_id, group in df.groupby("shopify_order_id", sort=False):
        row_number = int(group["row_number"].iloc[0])
        try:
            good.append(build_one_order(shopify_id, group, mapping, product_ids, customer_ids))
        except ValueError as error:
            payload = {
                "shopify_order_id": shopify_id,
                "order_number": first_nonblank(group["order_number"]),
            }
            rejected.append(rejection("orders", row_number, str(error), payload))
    return good, rejected


def start_batch(engine, file_name, source_name, data_source="shopify_csv"):
    sql = text(
        """
        INSERT INTO staging.etl_batches (source_name, file_name, data_source)
        VALUES (:source_name, :file_name, :data_source)
        RETURNING batch_id
        """
    )
    with engine.begin() as connection:
        return connection.execute(
            sql,
            {"source_name": source_name, "file_name": file_name, "data_source": data_source},
        ).scalar()


def finish_batch(engine, batch_id, status, rows_read, rows_loaded, rows_rejected):
    sql = text(
        """
        UPDATE staging.etl_batches
        SET finished_at = now(), status = :status, rows_read = :rows_read,
            rows_loaded = :rows_loaded, rows_rejected = :rows_rejected
        WHERE batch_id = :batch_id
        """
    )
    with engine.begin() as connection:
        connection.execute(
            sql,
            {
                "status": status,
                "rows_read": rows_read,
                "rows_loaded": rows_loaded,
                "rows_rejected": rows_rejected,
                "batch_id": batch_id,
            },
        )


def save_rejected(connection, batch_id, rejected):
    if not rejected:
        return
    sql = text(
        """
        INSERT INTO staging.rejected_rows (batch_id, entity, row_number, reason, payload)
        VALUES (:batch_id, :entity, :row_number, :reason, CAST(:payload AS JSONB))
        """
    )
    records = [
        {**item, "batch_id": batch_id, "payload": json.dumps(item["payload"], ensure_ascii=False)}
        for item in rejected
    ]
    connection.execute(sql, records)


def print_summary(entity, records_read, loaded, rejected):
    print(f"{entity}: read {records_read}, loaded {loaded}, rejected {len(rejected)}")
    for reason, count in Counter(item["reason"] for item in rejected).most_common():
        print(f"  {count} x {reason}")


def load_customers(engine, mapping, path):
    df = read_allowlisted(path, mapping["customer_columns"])
    batch_id = start_batch(engine, path.name, "shopify_customers")
    records_read = df["shopify_customer_id"].nunique()
    try:
        good, rejected = build_customers(df)
        with engine.begin() as connection:
            for customer in good:
                updated = connection.execute(UPDATE_CUSTOMER, customer).rowcount
                if updated == 0:
                    connection.execute(INSERT_CUSTOMER, customer)
            save_rejected(connection, batch_id, rejected)
        finish_batch(engine, batch_id, "succeeded", records_read, len(good), len(rejected))
    except Exception:
        finish_batch(engine, batch_id, "failed", records_read, 0, 0)
        raise
    print_summary("customers", records_read, len(good), rejected)


def load_orders(engine, mapping, path):
    df = read_allowlisted(path, mapping["order_columns"])
    batch_id = start_batch(engine, path.name, "shopify_orders")
    records_read = df["shopify_order_id"].nunique()
    try:
        with engine.connect() as connection:
            product_rows = connection.execute(
                text("SELECT product_id, product_url FROM core.products")
            ).all()
            customer_rows = connection.execute(
                text(
                    "SELECT shopify_customer_id, customer_id FROM core.customers"
                    " WHERE shopify_customer_id IS NOT NULL"
                )
            ).all()
        product_ids = {url.rsplit("/", 1)[-1]: pid for pid, url in product_rows if url}
        customer_ids = {sid: cid for sid, cid in customer_rows}

        good, rejected = build_orders(df, mapping, product_ids, customer_ids)
        with engine.begin() as connection:
            for order in good:
                params = {key: value for key, value in order.items() if key != "items"}
                order_id = connection.execute(UPSERT_ORDER, params).scalar()
                connection.execute(DELETE_ITEMS, {"order_id": order_id})
                connection.execute(
                    INSERT_ITEM, [{**item, "order_id": order_id} for item in order["items"]]
                )
            save_rejected(connection, batch_id, rejected)
        finish_batch(engine, batch_id, "succeeded", records_read, len(good), len(rejected))
    except Exception:
        finish_batch(engine, batch_id, "failed", records_read, 0, 0)
        raise
    print_summary("orders", records_read, len(good), rejected)


def main():
    parser = argparse.ArgumentParser(description="Load Shopify export files")
    parser.add_argument("--customers", type=Path)
    parser.add_argument("--orders", type=Path)
    args = parser.parse_args()
    if not args.customers and not args.orders:
        parser.error("give --customers, --orders, or both")

    mapping = load_mapping()
    engine = get_engine()
    for path in (args.customers, args.orders):
        if path and "fixtures" in str(path).lower() and not engine.url.database.endswith("_test"):
            parser.error(f"{path} is a test fixture and may only be loaded into a *_test database")
    print("database:", engine.url.database)
    if args.customers:
        load_customers(engine, mapping, args.customers)
    if args.orders:
        load_orders(engine, mapping, args.orders)


if __name__ == "__main__":
    main()