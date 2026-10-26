import csv
import time
from pathlib import Path

import requests

BASE_URL = "https://narrative-platform.com/collections.json"
OUTPUT = Path("data/raw/collections_raw.csv")
HEADERS = {"User-Agent": "catalog-reader (contact: soultanyousif@outlook.com)"}


def fetch_all_collections():
    collections = []
    page = 1
    while True:
        response = requests.get(
            BASE_URL,
            params={"limit": 250, "page": page},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        batch = response.json().get("collections", [])
        if not batch:
            break
        collections.extend(batch)
        page += 1
        time.sleep(1)
    return collections


def main():
    collections = fetch_all_collections()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["handle", "title", "products_count"])
        for c in collections:
            writer.writerow([c.get("handle", ""), c.get("title", ""), c.get("products_count", 0)])
    print(f"Saved {len(collections)} collections to {OUTPUT}")
    for c in sorted(collections, key=lambda c: -c.get("products_count", 0)):
        print(c.get("products_count", 0), "|", c.get("title", ""), "|", c.get("handle", ""))


if __name__ == "__main__":
    main()