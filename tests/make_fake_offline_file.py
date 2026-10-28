from pathlib import Path

import pandas as pd

PRODUCTS = Path("data/seed/products.csv")
OUTPUT = Path("data/fixtures/offline_fake/offline_sales.xlsx")


def row(receipt, date, sku, quantity, price="", email=""):
    return {
        "receipt_number": receipt,
        "sale_date": date,
        "sku": sku,
        "product_name_auto": "",
        "quantity": quantity,
        "unit_price_jpy": price,
        "customer_email": email,
    }


def main():
    products = pd.read_csv(PRODUCTS)
    products = products[products["price_jpy"] >= 3000].head(5)
    a, b, c, d, e = list(products["sku"])
    price_c = int(products.iloc[2]["price_jpy"])

    rows = [
        row("R-1001", "2026-10-20", a, 1),
        row("R-1001", "2026-10-20", b, 2),
        row("R-1002", "2026-10-21", c, 1, price_c - 1000, "fake.alpha@example.com"),
        row("R-1003", "2026-10-22", d, 1),
        row("R-1004", "2026-10-22", "NP-9999", 1),
        row("R-1005", "2026-10-23", a, 0),
        row("R-1006", "2099-01-01", a, 1),
        row("R-1007", "2026-10-23", a, 1, "", "bad-email"),
        row("R-1008", "2026-10-23", e, 1, 3000),
        row("R-1008", "2026-10-23", e, 1, 3500),
        row("R-1009", "2026-10-24", a, 1, "", "fake.zeta@example.com"),
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(OUTPUT, sheet_name="Sales", index=False)
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()