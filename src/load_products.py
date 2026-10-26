import pandas as pd
from sqlalchemy import text

from db import get_engine

UPSERT = text(
    """
    INSERT INTO core.products (sku, name, maker, category, price_jpy, product_url)
    VALUES (:sku, :name, :maker, :category, :price_jpy, :product_url)
    ON CONFLICT (sku) DO UPDATE SET
        name = EXCLUDED.name,
        maker = EXCLUDED.maker,
        category = EXCLUDED.category,
        price_jpy = EXCLUDED.price_jpy,
        product_url = EXCLUDED.product_url
    """
)


def main():
    products = pd.read_csv("data/seed/products.csv")
    columns = ["sku", "name", "maker", "category", "price_jpy", "product_url"]
    records = products[columns].to_dict("records")

    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(UPSERT, records)
        count = connection.execute(text("SELECT COUNT(*) FROM core.products")).scalar()
    print("products in database:", count)


if __name__ == "__main__":
    main()