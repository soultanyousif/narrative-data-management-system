import pandas as pd
from sqlalchemy import text

import check_data
import shopify_loader
from conftest import load_all


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def test_shopify_load_counts(loaded):
    assert scalar(loaded, "SELECT COUNT(*) FROM core.orders WHERE data_source = 'shopify_csv'") == 8
    assert scalar(loaded, "SELECT COUNT(*) FROM core.customers WHERE data_source = 'shopify_csv'") == 5


def test_statuses_and_refunds(loaded):
    with loaded.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT order_number, status, refund_jpy, channel FROM core.orders "
                "WHERE data_source = 'shopify_csv'"
            )
        ).all()
    by_name = {row.order_number: row for row in rows}
    assert by_name["#FAKE-1002"].status == "fulfilled"
    assert by_name["#FAKE-1003"].status == "cancelled"
    assert by_name["#FAKE-1004"].status == "paid"
    assert by_name["#FAKE-1004"].refund_jpy == 1000
    assert by_name["#FAKE-1005"].status == "refunded"
    assert by_name["#FAKE-1007"].channel == "offline"


def test_rejections_are_recorded_with_reasons(loaded):
    with loaded.connect() as connection:
        reasons = [row[0] for row in connection.execute(text("SELECT reason FROM staging.rejected_rows"))]
    assert len(reasons) == 10
    joined = " | ".join(reasons)
    for expected in [
        "email is missing or invalid",
        "not in the catalog",
        "not supported yet",
        "does not match subtotal",
        "customer is not in the database",
        "must be a whole number",
        "in the future",
        "email is invalid",
        "different prices",
    ]:
        assert expected in joined


def test_offline_receipts(loaded):
    with loaded.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT o.order_number, c.email FROM core.orders o "
                "LEFT JOIN core.customers c USING (customer_id) "
                "WHERE o.data_source = 'offline_csv' ORDER BY 1"
            )
        ).all()
    assert [row.order_number for row in rows] == ["R-1001", "R-1002", "R-1003", "R-1009"]
    emails = {row.order_number: row.email for row in rows}
    assert emails["R-1002"] == "fake.alpha@example.com"
    assert emails["R-1003"] is None
    assert emails["R-1009"] == "fake.zeta@example.com"


def test_integrity_checks_pass(loaded):
    with loaded.connect() as connection:
        for name, sql, expected in check_data.CHECKS:
            assert connection.execute(text(sql)).scalar() == expected, name


def test_rerun_changes_nothing(loaded):
    count_sql = (
        "SELECT (SELECT COUNT(*) FROM core.orders), (SELECT COUNT(*) FROM core.order_items), "
        "(SELECT COUNT(*) FROM core.customers)"
    )
    with loaded.connect() as connection:
        before = tuple(connection.execute(text(count_sql)).one())
    load_all(loaded)
    with loaded.connect() as connection:
        after = tuple(connection.execute(text(count_sql)).one())
    assert before == after


def test_offline_customer_later_seen_in_shopify(loaded, tmp_path):
    path = tmp_path / "Customers.csv"
    pd.DataFrame(
        [
            {
                "ID": "8001",
                "Email": "fake.zeta@example.com",
                "Language": "ja-JP",
                "Created At": "2026-10-24T10:00:00+09:00",
                "Address Country Code": "JP",
                "Address Is Default": "true",
            }
        ]
    ).to_csv(path, index=False)
    shopify_loader.load_customers(loaded, shopify_loader.load_mapping(), path)
    with loaded.connect() as connection:
        rows = connection.execute(
            text("SELECT shopify_customer_id FROM core.customers WHERE email = 'fake.zeta@example.com'")
        ).all()
    assert len(rows) == 1
    assert rows[0].shopify_customer_id == "8001"