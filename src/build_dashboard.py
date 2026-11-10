import os
import sys
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("METABASE_URL", "http://localhost:3000").rstrip("/")
EMAIL = os.environ["METABASE_ADMIN_EMAIL"]
PASSWORD = os.environ["METABASE_ADMIN_PASSWORD"]
DATABASE_NAME = "Narrative Platform (reporting)"
COLLECTION_NAME = "Narrative Platform dashboard"
DASHBOARD_NAME = "Narrative Platform dashboard (practice data)"

session = requests.Session()

FILTER_SQL = (
    "[[AND order_date >= {{start_date}}]] "
    "[[AND order_date <= {{end_date}}]] "
    "[[AND country_code = {{country}}]] "
    "[[AND channel = {{channel}}]]"
)

FILTER_PARAMETERS = [
    {"id": "start_date", "name": "Start date", "slug": "start_date", "type": "date/single"},
    {"id": "end_date", "name": "End date", "slug": "end_date", "type": "date/single"},
    {"id": "country", "name": "Country", "slug": "country", "type": "string/="},
    {"id": "channel", "name": "Channel", "slug": "channel", "type": "string/="},
]


def call(method, path, payload=None):
    response = session.request(method, f"{BASE_URL}/api{path}", json=payload, timeout=120)
    if not response.ok:
        print("FAILED:", method, path, response.status_code)
        print(response.text[:3000])
        sys.exit(1)
    return response.json() if response.text else None


def login():
    response = requests.post(
        f"{BASE_URL}/api/session",
        json={"username": EMAIL, "password": PASSWORD},
        timeout=60,
    )
    if not response.ok:
        print("Login to Metabase failed:", response.status_code, response.text[:500])
        sys.exit(1)
    session.headers["X-Metabase-Session"] = response.json()["id"]


def find_database():
    data = call("GET", "/database")
    items = data["data"] if isinstance(data, dict) else data
    for item in items:
        if item["name"] == DATABASE_NAME:
            return item["id"]
    sys.exit(f"Database {DATABASE_NAME!r} was not found in Metabase")


def reset_collection():
    for collection in call("GET", "/collection"):
        if collection.get("name") == COLLECTION_NAME and not collection.get("archived"):
            call("PUT", f"/collection/{collection['id']}", {"archived": True})
    return call("POST", "/collection", {"name": COLLECTION_NAME})["id"]


def filter_tags():
    def tag(name, label, kind):
        return {
            "id": str(uuid.uuid4()),
            "name": name,
            "display-name": label,
            "type": kind,
            "required": False,
        }

    return {
        "start_date": tag("start_date", "Start date", "date"),
        "end_date": tag("end_date", "End date", "date"),
        "country": tag("country", "Country", "text"),
        "channel": tag("channel", "Channel", "text"),
    }


def card(title, sql, display, row, col, w, h, filtered=False, viz=None):
    return {
        "title": title,
        "sql": sql,
        "display": display,
        "filtered": filtered,
        "viz": viz or {},
        "row": row,
        "col": col,
        "w": w,
        "h": h,
    }


def note(markdown, row, col, w, h):
    return {"text": markdown, "row": row, "col": col, "w": w, "h": h}


def bar(dimensions, metrics, stacked=False, ordinal=False):
    settings = {"graph.dimensions": dimensions, "graph.metrics": metrics}
    if stacked:
        settings["stackable.stack_type"] = "stacked"
    if ordinal:
        settings["graph.x_axis.scale"] = "ordinal"
    return settings


F = "__F__"

PAGES = [
    {
        "name": "Overview",
        "items": [
            card("Revenue (JPY)",
                 f"SELECT SUM(net_revenue_jpy) AS revenue_jpy FROM reporting.orders WHERE is_counted {F}",
                 "scalar", 0, 0, 6, 3, True),
            card("Orders",
                 f"SELECT COUNT(*) AS orders FROM reporting.orders WHERE is_counted {F}",
                 "scalar", 0, 6, 6, 3, True),
            card("Customers",
                 "SELECT COUNT(DISTINCT customer_id) AS customers FROM reporting.orders "
                 f"WHERE is_counted AND customer_id IS NOT NULL {F}",
                 "scalar", 0, 12, 6, 3, True),
            card("Average order value (JPY)",
                 "SELECT ROUND(SUM(net_revenue_jpy)::numeric / NULLIF(COUNT(*), 0)) "
                 f"AS average_order_value_jpy FROM reporting.orders WHERE is_counted {F}",
                 "scalar", 0, 18, 6, 3, True),
            card("Monthly revenue",
                 "SELECT order_month AS month, SUM(net_revenue_jpy) AS revenue_jpy "
                 f"FROM reporting.orders WHERE is_counted {F} GROUP BY 1 ORDER BY 1",
                 "bar", 3, 0, 12, 7, True, bar(["month"], ["revenue_jpy"])),
            card("Revenue by channel",
                 "SELECT order_month AS month, channel, SUM(net_revenue_jpy) AS revenue_jpy "
                 f"FROM reporting.orders WHERE is_counted {F} GROUP BY 1, 2 ORDER BY 1, 2",
                 "bar", 3, 12, 12, 7, True, bar(["month", "channel"], ["revenue_jpy"], stacked=True)),
            card("Revenue by category",
                 "SELECT category, ROUND(SUM(net_revenue_jpy)) AS revenue_jpy "
                 f"FROM reporting.order_lines WHERE is_counted {F} GROUP BY 1 ORDER BY 2 DESC",
                 "pie", 10, 0, 12, 8, True),
            card("Repeat customers, all time (%)",
                 "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE is_repeat_customer) "
                 "/ NULLIF(COUNT(*) FILTER (WHERE counted_orders > 0), 0), 1) AS repeat_customers_percent "
                 "FROM reporting.customer_summary",
                 "scalar", 10, 12, 6, 4),
            card("Orders without a customer record (%)",
                 "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE customer_type = 'guest') "
                 f"/ NULLIF(COUNT(*), 0), 1) AS guest_orders_percent FROM reporting.orders WHERE is_counted {F}",
                 "scalar", 10, 18, 6, 4, True),
            note("**How to read this page.** Revenue counts paid and fulfilled orders, tax included, "
                 "shipping excluded, with refunds subtracted. The filters at the top apply to the sales "
                 "charts. Dates are in Japan time.", 14, 12, 12, 4),
        ],
    },
    {
        "name": "Customers",
        "items": [
            card("New and returning customers per month",
                 "SELECT order_month AS month, customer_type, COUNT(DISTINCT customer_id) AS customers "
                 "FROM reporting.orders WHERE is_counted AND customer_id IS NOT NULL "
                 f"{F} GROUP BY 1, 2 ORDER BY 1, 2",
                 "bar", 0, 0, 14, 7, True, bar(["month", "customer_type"], ["customers"], stacked=True)),
            card("Customer segments (all time)",
                 "SELECT segment, COUNT(*) AS customers FROM reporting.customer_summary "
                 "WHERE counted_orders > 0 GROUP BY 1 ORDER BY 2 DESC",
                 "pie", 0, 14, 10, 7),
            card("Orders per customer (all time)",
                 "SELECT counted_orders AS orders_per_customer, COUNT(*) AS customers "
                 "FROM reporting.customer_summary WHERE counted_orders > 0 GROUP BY 1 ORDER BY 1",
                 "bar", 7, 0, 12, 6, False, bar(["orders_per_customer"], ["customers"], ordinal=True)),
            card("Customers by country (all time)",
                 "SELECT country_code, COUNT(*) AS customers FROM reporting.customer_summary "
                 "WHERE counted_orders > 0 GROUP BY 1 ORDER BY 2 DESC",
                 "bar", 7, 12, 12, 6, False, bar(["country_code"], ["customers"])),
            card("Top 10 customers by lifetime revenue",
                 "SELECT customer_id, country_code, counted_orders, lifetime_revenue_jpy, "
                 "first_order_date, last_order_date FROM reporting.customer_summary "
                 "ORDER BY lifetime_revenue_jpy DESC LIMIT 10",
                 "table", 13, 0, 24, 7),
            note("Customers are shown by ID only. Names, emails and addresses are never loaded "
                 "into the dashboard.", 20, 0, 24, 2),
        ],
    },
    {
        "name": "Sales and markets",
        "items": [
            card("Revenue by country",
                 "SELECT country_code, SUM(net_revenue_jpy) AS revenue_jpy FROM reporting.orders "
                 f"WHERE is_counted {F} GROUP BY 1 ORDER BY 2 DESC",
                 "bar", 0, 0, 12, 7, True, bar(["country_code"], ["revenue_jpy"])),
            card("Revenue by channel (share)",
                 "SELECT channel, SUM(net_revenue_jpy) AS revenue_jpy FROM reporting.orders "
                 f"WHERE is_counted {F} GROUP BY 1 ORDER BY 2 DESC",
                 "pie", 0, 12, 6, 7, True),
            card("Revenue by currency",
                 "SELECT currency, SUM(net_revenue_jpy) AS revenue_jpy FROM reporting.orders "
                 f"WHERE is_counted {F} GROUP BY 1 ORDER BY 2 DESC",
                 "bar", 0, 18, 6, 7, True, bar(["currency"], ["revenue_jpy"])),
            card("Orders and average order value by country",
                 "SELECT country_code, COUNT(*) AS orders, "
                 "ROUND(SUM(net_revenue_jpy)::numeric / NULLIF(COUNT(*), 0)) AS average_order_value_jpy, "
                 f"SUM(net_revenue_jpy) AS revenue_jpy FROM reporting.orders WHERE is_counted {F} "
                 "GROUP BY 1 ORDER BY 4 DESC",
                 "table", 7, 0, 12, 8, True),
            card("Top 15 makers by revenue",
                 "SELECT maker, ROUND(SUM(net_revenue_jpy)) AS revenue_jpy FROM reporting.order_lines "
                 f"WHERE is_counted {F} GROUP BY 1 ORDER BY 2 DESC LIMIT 15",
                 "row", 7, 12, 12, 8, True, bar(["maker"], ["revenue_jpy"])),
            card("Revenue by country and category",
                 "SELECT country_code, category, ROUND(SUM(net_revenue_jpy)) AS revenue_jpy, "
                 f"SUM(units_sold) AS units FROM reporting.order_lines WHERE is_counted {F} "
                 "GROUP BY 1, 2 ORDER BY 1, 3 DESC",
                 "table", 15, 0, 24, 9, True),
        ],
    },
    {
        "name": "Products and inventory",
        "items": [
            card("Units in stock",
                 "SELECT SUM(stock_on_hand) AS units_in_stock FROM reporting.product_performance",
                 "scalar", 0, 0, 6, 3),
            card("Low stock products",
                 "SELECT COUNT(*) AS low_stock_products FROM reporting.product_performance WHERE is_low_stock",
                 "scalar", 0, 6, 6, 3),
            card("Slow movers",
                 "SELECT COUNT(*) AS slow_movers FROM reporting.product_performance WHERE is_slow_mover",
                 "scalar", 0, 12, 6, 3),
            card("Products never sold",
                 "SELECT COUNT(*) AS never_sold FROM reporting.product_performance WHERE units_sold = 0",
                 "scalar", 0, 18, 6, 3),
            card("Top 15 products by revenue",
                 "SELECT product_name, maker, category, SUM(units_sold) AS units, "
                 "ROUND(SUM(net_revenue_jpy)) AS revenue_jpy FROM reporting.order_lines "
                 f"WHERE is_counted {F} GROUP BY product_id, product_name, maker, category "
                 "ORDER BY 5 DESC LIMIT 15",
                 "table", 3, 0, 24, 8, True),
            card("Low stock list",
                 "SELECT product_name, maker, category, stock_on_hand, units_last_30d, days_of_cover "
                 "FROM reporting.product_performance WHERE is_low_stock "
                 "ORDER BY stock_on_hand, days_of_cover NULLS LAST LIMIT 50",
                 "table", 11, 0, 12, 9),
            card("Slow movers by stock value",
                 "SELECT product_name, maker, category, stock_on_hand, price_jpy, "
                 "stock_on_hand * price_jpy AS stock_value_jpy, last_sale_date "
                 "FROM reporting.product_performance WHERE is_slow_mover "
                 "ORDER BY stock_value_jpy DESC LIMIT 50",
                 "table", 11, 12, 12, 9),
        ],
    },
    {
        "name": "Data health",
        "items": [
            card("Rows by source",
                 "SELECT item, data_source, row_count, latest_at FROM reporting.data_health "
                 "ORDER BY item, data_source",
                 "table", 0, 0, 24, 6),
            card("Latest load batches",
                 "SELECT batch_id, source_name, file_name, data_source, started_at, status, "
                 "rows_read, rows_loaded, rows_rejected FROM reporting.load_batches "
                 "ORDER BY batch_id DESC LIMIT 20",
                 "table", 6, 0, 24, 6),
            card("Rejected rows by reason",
                 "SELECT source_name, entity, reason, rejected_rows FROM reporting.rejection_reasons "
                 "ORDER BY rejected_rows DESC",
                 "table", 12, 0, 12, 6),
            note("**About this page.** Every row carries its source: synthetic (practice data), "
                 "offline_csv (Excel template) or shopify_csv (Shopify exports). Rows that fail the "
                 "checks during an import are listed here with the reason; nothing is dropped "
                 "silently. All figures follow the definitions in docs/metrics.md.", 12, 12, 12, 6),
        ],
    },
]


def create_card(spec, database_id, collection_id):
    sql = spec["sql"].replace(F, FILTER_SQL if spec["filtered"] else "")
    tags = filter_tags() if spec["filtered"] else {}
    created = call(
        "POST",
        "/card",
        {
            "name": spec["title"],
            "type": "question",
            "display": spec["display"],
            "dataset_query": {
                "type": "native",
                "database": database_id,
                "native": {"query": sql, "template-tags": tags},
            },
            "visualization_settings": spec["viz"],
            "collection_id": collection_id,
        },
    )
    return created["id"]


def build_dashboard(collection_id):
    dashboard = call(
        "POST",
        "/dashboard",
        {
            "name": DASHBOARD_NAME,
            "collection_id": collection_id,
            "parameters": FILTER_PARAMETERS,
        },
    )
    tabs, dashcards = [], []
    for page_number, page in enumerate(PAGES, start=1):
        tab_id = -page_number
        tabs.append({"id": tab_id, "name": page["name"]})
        for item in page["items"]:
            dashcard = {
                "id": -(len(dashcards) + 1),
                "dashboard_tab_id": tab_id,
                "row": item["row"],
                "col": item["col"],
                "size_x": item["w"],
                "size_y": item["h"],
            }
            if "text" in item:
                dashcard.update(
                    {
                        "card_id": None,
                        "parameter_mappings": [],
                        "visualization_settings": {
                            "virtual_card": {
                                "name": None,
                                "display": "text",
                                "visualization_settings": {},
                                "dataset_query": {},
                                "archived": False,
                            },
                            "text": item["text"],
                        },
                    }
                )
            else:
                mappings = []
                if item["filtered"]:
                    mappings = [
                        {
                            "parameter_id": p["id"],
                            "card_id": item["card_id"],
                            "target": ["variable", ["template-tag", p["id"]]],
                        }
                        for p in FILTER_PARAMETERS
                    ]
                dashcard.update(
                    {
                        "card_id": item["card_id"],
                        "parameter_mappings": mappings,
                        "visualization_settings": {},
                    }
                )
            dashcards.append(dashcard)

    call(
        "PUT",
        f"/dashboard/{dashboard['id']}",
        {"tabs": tabs, "dashcards": dashcards, "parameters": FILTER_PARAMETERS},
    )
    return dashboard["id"]


def main():
    login()
    database_id = find_database()
    collection_id = reset_collection()
    for page in PAGES:
        print("creating charts for", page["name"])
        for item in page["items"]:
            if "text" not in item:
                item["card_id"] = create_card(item, database_id, collection_id)
    dashboard_id = build_dashboard(collection_id)
    print()
    print("Dashboard ready:", f"{BASE_URL}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()