import os
import sys
from pathlib import Path

os.environ["TARGET_DB"] = "narrative_test"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

import pytest
from sqlalchemy import text

import load_products
import offline_loader
import shopify_loader
from db import get_engine

SHOPIFY_DIR = Path("data/fixtures/shopify_fake")
OFFLINE_FILE = Path("data/fixtures/offline_fake/offline_sales.xlsx")


def load_all(engine):
    mapping = shopify_loader.load_mapping()
    shopify_loader.load_customers(engine, mapping, SHOPIFY_DIR / "Customers.csv")
    shopify_loader.load_orders(engine, mapping, SHOPIFY_DIR / "Orders.csv")
    offline_loader.load_offline(engine, OFFLINE_FILE)


@pytest.fixture(scope="session")
def engine():
    engine = get_engine()
    if not engine.url.database.endswith("_test"):
        pytest.exit("tests may only run on a *_test database")
    return engine


@pytest.fixture(scope="session")
def loaded(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE core.order_items, core.orders, core.customers, "
                "core.inventory_snapshots, staging.rejected_rows, staging.raw_rows, "
                "staging.etl_batches RESTART IDENTITY CASCADE"
            )
        )
    load_products.main()
    load_all(engine)
    return engine