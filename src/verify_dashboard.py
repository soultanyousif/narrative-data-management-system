import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import text

from db import get_engine

load_dotenv()

BASE_URL = os.environ.get("METABASE_URL", "http://localhost:3000").rstrip("/")
EMAIL = os.environ["METABASE_ADMIN_EMAIL"]
PASSWORD = os.environ["METABASE_ADMIN_PASSWORD"]

REVENUE_SPLITS = [
    "Monthly revenue",
    "Revenue by channel",
    "Revenue by country",
    "Revenue by currency",
    "Revenue by channel (share)",
    "Revenue by category",
]


def login(session):
    response = requests.post(
        f"{BASE_URL}/api/session",
        json={"username": EMAIL, "password": PASSWORD},
        timeout=60,
    )
    response.raise_for_status()
    session.headers["X-Metabase-Session"] = response.json()["id"]


def expected_numbers():
    engine = get_engine()
    with engine.connect() as connection:
        orders = pd.read_sql(
            text("SELECT customer_id, status, amount_jpy, refund_jpy FROM core.orders"),
            connection,
        )
    counted = orders[orders["status"].isin(["paid", "fulfilled"])]
    refunds_applied = counted[["amount_jpy", "refund_jpy"]].min(axis=1)
    revenue = int((counted["amount_jpy"] - refunds_applied).sum())
    return {
        "Revenue (JPY)": revenue,
        "Orders": len(counted),
        "Customers": counted["customer_id"].dropna().nunique(),
        "Average order value (JPY)": round(revenue / len(counted)),
    }


def run_card(session, card_id):
    response = session.post(
        f"{BASE_URL}/api/card/{card_id}/query", json={"parameters": []}, timeout=180
    )
    body = response.json()
    if not response.ok or body.get("status") == "failed" or body.get("error"):
        return None, str(body.get("error", response.text))[:200]
    return body["data"]["rows"], ""


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python src\\verify_dashboard.py <dashboard id>")

    session = requests.Session()
    login(session)
    dashboard = session.get(f"{BASE_URL}/api/dashboard/{sys.argv[1]}", timeout=60).json()
    tabs = {tab["id"]: tab["name"] for tab in dashboard.get("tabs", [])}

    results = {}
    problems = 0
    for dashcard in dashboard["dashcards"]:
        card_id = dashcard.get("card_id")
        if not card_id:
            continue
        name = dashcard["card"]["name"]
        tab = tabs.get(dashcard.get("dashboard_tab_id"), "")
        rows, error = run_card(session, card_id)
        if rows is None:
            problems += 1
            print(f"FAIL | {tab} | {name} | {error}")
            continue
        results[name] = rows
        print(f"ok   | {tab} | {name} | {len(rows)} rows")

    print()
    expected = expected_numbers()
    for name, value in expected.items():
        rows = results.get(name)
        got = rows[0][0] if rows else None
        passed = got is not None and abs(float(got) - value) <= 1
        problems += 0 if passed else 1
        print(f"{'PASS' if passed else 'FAIL'} | {name} | dashboard {got}, independent {value}")

    revenue = expected["Revenue (JPY)"]
    for name in REVENUE_SPLITS:
        rows = results.get(name)
        total = sum(float(row[-1]) for row in rows) if rows else None
        passed = total is not None and abs(total - revenue) <= 3
        problems += 0 if passed else 1
        print(f"{'PASS' if passed else 'FAIL'} | {name} adds up to {total}, revenue is {revenue}")

    print()
    print("everything matches" if problems == 0 else f"{problems} problem(s) found")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()