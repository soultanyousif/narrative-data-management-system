import csv
import time
from pathlib import Path

import requests

BASE_URL = "https://narrative-platform.com/products.json"
OUTPUT = Path("data/raw/catalog_raw.csv")
HEADERS = {"User-Agent": "catalog-reader (contact: soultanyousif@outlook.com)"}


def fetch_all_products():
    products = []
    page = 1
    while True:
        response = requests.get(
            BASE_URL,
            params={"limit": 250, "page": page},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        batch = response.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        page += 1
        time.sleep(1)
    return products


def main():
    products = fetch_all_products()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["handle", "title", "vendor", "product_type", "price", "variant_count", "tags"]
        )
        for product in products:
            variants = product.get("variants", [])
            first = variants[0] if variants else {}
            writer.writerow(
                [
                    product.get("handle", ""),
                    product.get("title", ""),
                    product.get("vendor", ""),
                    product.get("product_type", ""),
                    first.get("price", ""),
                    len(variants),
                    ",".join(product.get("tags", [])),
                ]
            )
    print(f"Saved {len(products)} products to {OUTPUT}")


if __name__ == "__main__":
    main()