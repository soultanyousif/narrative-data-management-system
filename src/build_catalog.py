import re
import time
from pathlib import Path

import pandas as pd
import requests

SITE = "https://narrative-platform.com"
HEADERS = {"User-Agent": "catalog-reader (contact: soultanyousif@outlook.com)"}
OUTPUT = Path("data/seed/products.csv")

CATEGORY_BY_DIGIT = {
    "1": "Tableware & Dining",
    "2": "Interior & Home Decor",
    "3": "Bags & Accessories",
    "4": "Jewelry",
    "5": "Lifestyle Goods & Miscellaneous",
}
DEFAULT_CATEGORY = "Lifestyle Goods & Miscellaneous"
CATEGORY_PATTERN = re.compile(r"^(\d)(?:\.\d+)? - ")
MAKER_PREFIX = "メーカー - "


def handles_in_collection(collection_handle):
    handles = []
    page = 1
    while True:
        response = requests.get(
            f"{SITE}/collections/{collection_handle}/products.json",
            params={"limit": 250, "page": page},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        batch = response.json().get("products", [])
        if not batch:
            break
        handles.extend(p["handle"] for p in batch)
        page += 1
        time.sleep(1)
    return handles


def read_memberships(collections):
    digits_by_product = {}
    makers_by_product = {}
    for row in collections.itertuples():
        category_match = CATEGORY_PATTERN.match(row.title)
        is_maker = row.title.startswith(MAKER_PREFIX)
        if not category_match and not is_maker:
            continue
        print("reading collection:", row.title)
        for handle in handles_in_collection(row.handle):
            if category_match:
                digits_by_product.setdefault(handle, set()).add(category_match.group(1))
            if is_maker:
                maker_name = row.title[len(MAKER_PREFIX):].strip()
                makers_by_product.setdefault(handle, []).append(maker_name)
    return digits_by_product, makers_by_product


def main():
    products = pd.read_csv("data/raw/catalog_raw.csv")
    collections = pd.read_csv("data/raw/collections_raw.csv")
    collections = collections[collections["products_count"] > 0]

    digits_by_product, makers_by_product = read_memberships(collections)

    rows = []
    category_conflicts = 0
    maker_conflicts = 0
    sorted_products = products.sort_values("handle").reset_index(drop=True)

    for index, product in enumerate(sorted_products.itertuples(), start=1):
        digits = digits_by_product.get(product.handle, set())
        makers = makers_by_product.get(product.handle, [])

        if digits:
            category = CATEGORY_BY_DIGIT[min(digits)]
            category_source = "collection"
            if len(digits) > 1:
                category_conflicts += 1
        else:
            category = DEFAULT_CATEGORY
            category_source = "default"

        if makers:
            maker = makers[0]
            maker_source = "collection"
            if len(set(makers)) > 1:
                maker_conflicts += 1
        elif product.vendor != "Narrative Platform":
            maker = product.vendor
            maker_source = "vendor"
        else:
            maker = "Unspecified"
            maker_source = "default"

        rows.append(
            {
                "sku": f"NP-{index:04d}",
                "name": product.title,
                "maker": maker,
                "category": category,
                "price_jpy": int(float(product.price)),
                "product_url": f"{SITE}/products/{product.handle}",
                "category_source": category_source,
                "maker_source": maker_source,
            }
        )

    catalog = pd.DataFrame(rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(OUTPUT, index=False, encoding="utf-8")

    print()
    print("products:", len(catalog))
    print("category conflicts:", category_conflicts)
    print("maker conflicts:", maker_conflicts)
    print()
    print(catalog["category"].value_counts().to_string())
    print()
    print(catalog["category_source"].value_counts().to_string())
    print()
    print(catalog["maker_source"].value_counts().to_string())
    print()
    print(catalog["maker"].value_counts().head(15).to_string())


if __name__ == "__main__":
    main()