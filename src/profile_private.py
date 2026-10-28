from pathlib import Path

import pandas as pd

PRIVATE = Path("data/private")

SAFE_COLUMNS = {
    "order/Orders.csv": [
        "Currency",
        "Shop Currency",
        "Source",
        "Physical Location",
        "Payment: Status",
        "Order Fulfillment Status",
        "Cancel: Reason",
        "Tax: Included",
        "Tax 1: Title",
        "Tax 1: Rate",
        "Line: Type",
        "Top Row",
        "Transaction: Kind",
        "Transaction: Status",
        "Transaction: Test",
        "Fulfillment: Status",
        "Shipping: Country Code",
        "Line: Vendor",
    ],
    "customer/Customers.csv": [
        "State",
        "Language",
        "Address Country Code",
        "Address Is Default",
        "Top Row",
    ],
}


def show_counts(df, columns):
    for column in columns:
        if column not in df.columns:
            print(f"{column}: column not found")
            print()
            continue
        counts = df[column].replace("", "(blank)").value_counts().head(8)
        print(f"{column}:")
        print(counts.to_string())
        print()


def read(name):
    return pd.read_csv(PRIVATE / name, dtype=str, keep_default_na=False)


def main():
    orders = read("order/Orders.csv")
    print("ORDERS")
    print("rows:", len(orders), "| distinct orders:", orders["ID"].nunique())
    print("rows with a SKU:", int((orders["Line: SKU"] != "").sum()))

    handles = orders.loc[orders["Line: Product Handle"] != "", "Line: Product Handle"]
    catalog = pd.read_csv("data/seed/products.csv")
    catalog_handles = set(catalog["product_url"].str.rsplit("/", n=1).str[-1])
    print("rows with a product handle:", len(handles))
    print("of those, found in our catalog:", int(handles.isin(catalog_handles).sum()))
    print()
    show_counts(orders, SAFE_COLUMNS["order/Orders.csv"])

    customers = read("customer/Customers.csv")
    print("CUSTOMERS")
    print("rows:", len(customers), "| distinct customers:", customers["ID"].nunique())
    print()
    show_counts(customers, SAFE_COLUMNS["customer/Customers.csv"])


if __name__ == "__main__":
    main()