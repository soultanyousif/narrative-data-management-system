import csv
from pathlib import Path

import pandas as pd

HEADERS_DOC = Path("docs/shopify_headers.md")
PRODUCTS = Path("data/seed/products.csv")
OUTPUT = Path("data/fixtures/shopify_fake")


def read_headers():
    sections, current = {}, None
    for line in HEADERS_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Orders export"):
            current = "orders"
            sections[current] = []
        elif line.startswith("## Customers export"):
            current = "customers"
            sections[current] = []
        elif line.startswith("- ") and current:
            sections[current].append(line[2:])
    return sections


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, restval="", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def make_customers():
    def row(cid, email, country, default, top):
        return {
            "ID": cid,
            "Email": email,
            "Language": "ja-JP",
            "Created At": "2026-09-01T09:00:00+09:00",
            "Address Country Code": country,
            "Address Is Default": default,
            "Top Row": top,
        }

    return [
        row("7001", "fake.alpha@example.com", "JP", "true", "true"),
        row("7002", "fake.beta@example.com", "US", "true", "true"),
        row("7003", "fake.gamma@example.com", "", "false", "true"),
        row("7003", "", "FR", "true", ""),
        row("7004", "fake.delta@example.com", "", "", "true"),
        row("7005", "not-an-email", "JP", "true", "true"),
        row("7006", "fake.epsilon@example.com", "DE", "true", "true"),
    ]


def make_order(order_id, name, lines, source="web", payment="paid", fulfillment="unfulfilled",
               customer="", currency="JPY", country="JP", discount=0, shipping=800,
               refund=0, cancelled="", subtotal_adjust=0, rate=1, location=""):
    lines_total = sum(price * qty for _, price, qty in lines)
    subtotal = lines_total - discount + subtotal_adjust
    if refund == "full":
        refund = subtotal + shipping
    original = subtotal if currency == "JPY" else round(subtotal / rate, 2)
    order_fields = {
        "Name": name,
        "Created At": "2026-10-20T10:15:00+09:00",
        "Cancelled At": cancelled,
        "Currency": currency,
        "Source": source,
        "Physical Location": location,
        "Payment: Status": payment,
        "Order Fulfillment Status": fulfillment,
        "Customer: ID": customer,
        "Shipping: Country Code": country,
        "Billing: Country Code": country,
        "Price: Subtotal": original,
        "Price: Subtotal (Shop Currency)": subtotal,
        "Tax: Total (Shop Currency)": round(subtotal * 10 / 110),
        "Price: Total Shipping (Shop Currency)": shipping,
        "Price: Total Discount (Shop Currency)": discount,
        "Price: Total Refund (Shop Currency)": refund,
        "Tax: Included": "true",
        "Top Row": "true",
    }
    rows = []
    for index, (handle, price, qty) in enumerate(lines):
        row = {
            "ID": order_id,
            "Line: Type": "Line Item",
            "Line: Product Handle": handle,
            "Line: Quantity": qty,
            "Line: Price (Shop Currency)": price,
        }
        if index == 0:
            row.update(order_fields)
        rows.append(row)
    rows.append({"ID": order_id, "Line: Type": "Shipping Line", "Line: Price (Shop Currency)": shipping})
    rows.append({"ID": order_id, "Line: Type": "Transaction"})
    return rows


def main():
    headers = read_headers()
    products = pd.read_csv(PRODUCTS)
    products = products[products["price_jpy"] >= 2000].head(4)
    items = [(r.product_url.rsplit("/", 1)[-1], int(r.price_jpy)) for r in products.itertuples()]

    def line(index, qty):
        return (items[index][0], items[index][1], qty)

    orders = []
    orders += make_order("5001", "#FAKE-1001", [line(0, 1), line(1, 2)], customer="7001")
    orders += make_order("5002", "#FAKE-1002", [line(2, 1)], fulfillment="fulfilled", customer="7001", discount=500)
    orders += make_order("5003", "#FAKE-1003", [line(3, 1)], payment="voided", customer="7003", cancelled="2026-10-21T09:00:00+09:00")
    orders += make_order("5004", "#FAKE-1004", [line(0, 2)], payment="partially_refunded", customer="7001", refund=1000)
    orders += make_order("5005", "#FAKE-1005", [line(1, 1)], payment="refunded", customer="7006", refund="full")
    orders += make_order("5006", "#FAKE-1006", [line(2, 1)])
    orders += make_order("5007", "#FAKE-1007", [line(3, 1)], source="pos", fulfillment="fulfilled", shipping=0, location="Tokyo shop")
    orders += make_order("5008", "#FAKE-1008", [("no-such-product", 3000, 1)])
    orders += make_order("5009", "#FAKE-1009", [line(0, 1)], source="shopify_draft_order")
    orders += make_order("5010", "#FAKE-1010", [line(1, 1)], subtotal_adjust=100)
    orders += make_order("5011", "#FAKE-1011", [line(2, 1)], customer="9999")
    orders += make_order("5012", "#FAKE-1012", [line(3, 1)], customer="7002", currency="USD", country="US", rate=150)

    write_csv(OUTPUT / "Customers.csv", headers["customers"], make_customers())
    write_csv(OUTPUT / "Orders.csv", headers["orders"], orders)
    print("fake export written to", OUTPUT)


if __name__ == "__main__":
    main()