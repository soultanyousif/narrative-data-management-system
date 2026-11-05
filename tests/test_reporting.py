import pandas as pd
from sqlalchemy import text


def read(engine, sql):
    with engine.connect() as connection:
        return pd.read_sql(text(sql), connection)


def expected_revenue(engine):
    orders = read(engine, "SELECT status, amount_jpy, refund_jpy FROM core.orders")
    counted = orders[orders["status"].isin(["paid", "fulfilled"])]
    refunds_applied = counted[["amount_jpy", "refund_jpy"]].min(axis=1)
    return int((counted["amount_jpy"] - refunds_applied).sum())


def test_revenue_matches_independent_calculation(loaded):
    view_total = read(loaded, "SELECT SUM(net_revenue_jpy) AS total FROM reporting.orders")
    assert int(view_total["total"].iloc[0]) == expected_revenue(loaded)


def test_line_revenue_adds_up_to_the_same_total(loaded):
    lines = read(loaded, "SELECT SUM(net_revenue_jpy) AS total FROM reporting.order_lines")
    assert abs(float(lines["total"].iloc[0]) - expected_revenue(loaded)) < 0.01


def test_category_revenue_adds_up_to_the_same_total(loaded):
    by_category = read(
        loaded,
        "SELECT category, SUM(net_revenue_jpy) AS total FROM reporting.order_lines GROUP BY 1",
    )
    assert abs(float(by_category["total"].sum()) - expected_revenue(loaded)) < 0.01


def test_order_and_customer_counts(loaded):
    orders = read(loaded, "SELECT customer_id, status FROM core.orders")
    counted = orders[orders["status"].isin(["paid", "fulfilled"])]
    view_orders = read(loaded, "SELECT COUNT(*) AS n FROM reporting.orders WHERE is_counted")
    view_customers = read(
        loaded, "SELECT COUNT(*) AS n FROM reporting.customer_summary WHERE counted_orders > 0"
    )
    assert int(view_orders["n"].iloc[0]) == len(counted)
    assert int(view_customers["n"].iloc[0]) == counted["customer_id"].dropna().nunique()


def test_repeat_customers(loaded):
    orders = read(loaded, "SELECT customer_id, status FROM core.orders")
    counted = orders[orders["status"].isin(["paid", "fulfilled"])].dropna(subset=["customer_id"])
    expected = int((counted.groupby("customer_id").size() >= 2).sum())
    view = read(
        loaded, "SELECT COUNT(*) AS n FROM reporting.customer_summary WHERE is_repeat_customer"
    )
    assert int(view["n"].iloc[0]) == expected


def test_customer_types_match_independent_calculation(loaded):
    orders = read(loaded, "SELECT customer_id, status, ordered_at FROM core.orders")
    counted = orders[orders["status"].isin(["paid", "fulfilled"])].copy()
    tokyo = pd.to_datetime(counted["ordered_at"], utc=True).dt.tz_convert("Asia/Tokyo")
    counted["month"] = tokyo.dt.strftime("%Y-%m")
    counted["first_month"] = counted.groupby("customer_id")["month"].transform("min")

    expected = {}
    for row in counted.itertuples():
        if pd.isna(row.customer_id):
            label = "guest"
        elif row.first_month == row.month:
            label = "new"
        else:
            label = "returning"
        expected[label] = expected.get(label, 0) + 1

    view = read(
        loaded,
        "SELECT customer_type, COUNT(*) AS n FROM reporting.orders WHERE is_counted GROUP BY 1",
    )
    actual = dict(zip(view["customer_type"], view["n"].astype(int)))
    assert actual == expected


def test_a_later_order_makes_a_customer_returning(loaded):
    with loaded.connect() as connection:
        transaction = connection.begin()
        customer_id = connection.execute(
            text("SELECT customer_id FROM core.customers WHERE shopify_customer_id = '7001'")
        ).scalar()
        connection.execute(
            text(
                "INSERT INTO core.orders (order_number, data_source, customer_id, channel, "
                "country_code, status, currency, fx_rate_to_jpy, amount_original, amount_jpy, "
                "ordered_at) VALUES ('TEST-LATER', 'shopify_csv', :cid, 'online', 'JP', 'paid', "
                "'JPY', 1, 1000, 1000, '2026-11-15 03:00:00+00')"
            ),
            {"cid": customer_id},
        )
        later_type = connection.execute(
            text("SELECT customer_type FROM reporting.orders WHERE order_number = 'TEST-LATER'")
        ).scalar()
        earlier_new = connection.execute(
            text(
                "SELECT COUNT(*) FROM reporting.orders "
                "WHERE customer_id = :cid AND customer_type = 'new'"
            ),
            {"cid": customer_id},
        ).scalar()
        transaction.rollback()
    assert later_type == "returning"
    assert earlier_new >= 1


def test_every_product_has_one_performance_row(loaded):
    products = read(loaded, "SELECT COUNT(*) AS n FROM core.products")
    performance = read(loaded, "SELECT COUNT(*) AS n FROM reporting.product_performance")
    assert int(products["n"].iloc[0]) == int(performance["n"].iloc[0])


def test_data_health_lists_the_sources(loaded):
    health = read(loaded, "SELECT item, data_source FROM reporting.data_health")
    assert {"orders", "customers", "products"} <= set(health["item"])
    assert {"shopify_csv", "offline_csv"} <= set(health["data_source"])