from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from faker import Faker

CONFIG_PATH = Path("config/synthetic.yaml")
PRODUCTS_PATH = Path("data/seed/products.csv")
OUTPUT_DIR = Path("data/generated")
DATA_SOURCE = "synthetic"
ONE_WEEK = pd.Timedelta(days=7)


def load_config():
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def weighted_choice(rng, weights_by_key, size=None):
    keys = list(weights_by_key.keys())
    weights = np.array(list(weights_by_key.values()), dtype=float)
    weights = weights / weights.sum()
    return rng.choice(keys, size=size, p=weights)


def period_bounds(config):
    start = pd.Timestamp(str(config["period"]["start"]), tz="UTC")
    end = pd.Timestamp(str(config["period"]["end"]), tz="UTC")
    return start, end


def build_calendar(config):
    start, end = period_bounds(config)
    days = pd.date_range(start, end, freq="D")
    multipliers = config["monthly_multiplier"]
    weights = np.array([multipliers[day.month] for day in days], dtype=float)
    return days, weights / weights.sum()


def sample_timestamps(rng, calendar, count):
    days, probabilities = calendar
    day_positions = rng.choice(len(days), size=count, p=probabilities)
    seconds = rng.integers(0, 86400, size=count)
    return [
        days[position] + pd.Timedelta(seconds=int(second))
        for position, second in zip(day_positions, seconds)
    ]


def build_customers(rng, fake, config):
    online_count = config["customers"]["online_customers"]
    offline_count = config["customers"]["offline_only_customers"]

    online_countries = weighted_choice(rng, config["online_countries"], size=online_count)

    other_countries = {c: w for c, w in config["online_countries"].items() if c != "JP"}
    foreign = weighted_choice(rng, other_countries, size=offline_count)
    is_japan = rng.random(offline_count) < config["offline"]["customer_jp_share"]
    offline_countries = np.where(is_japan, "JP", foreign)

    rows = []
    all_countries = list(online_countries) + list(offline_countries)
    for number, country in enumerate(all_countries, start=1):
        rows.append(
            {
                "email": f"synthetic.customer{number:05d}@example.com",
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "country_code": str(country),
                "kind": "online" if number <= online_count else "offline_only",
            }
        )
    return pd.DataFrame(rows)


def build_online_orders(rng, config, calendar, customers):
    online = customers[customers["kind"] == "online"]
    counts = weighted_choice(rng, config["customers"]["orders_per_customer"], size=len(online))
    rows = []
    for customer, count in zip(online.itertuples(), counts):
        for timestamp in sorted(sample_timestamps(rng, calendar, int(count))):
            rows.append(
                {
                    "customer_email": customer.email,
                    "channel": "online",
                    "country_code": customer.country_code,
                    "ordered_at": timestamp,
                }
            )
    return rows


def build_offline_orders(rng, config, calendar, customers):
    settings = config["offline"]
    total = settings["orders"]
    timestamps = sample_timestamps(rng, calendar, total)

    online_emails = customers[customers["kind"] == "online"]["email"].to_numpy()
    offline_emails = customers[customers["kind"] == "offline_only"]["email"].to_numpy()

    anonymous = rng.random(total) < settings["anonymous_share"]
    from_online = rng.random(total) < settings["existing_online_customer_share"]

    needed = int(((~anonymous) & (~from_online)).sum())
    pool = list(rng.permutation(offline_emails))[:needed]
    while len(pool) < needed:
        pool.append(rng.choice(offline_emails))

    rows = []
    pool_position = 0
    for i in range(total):
        if anonymous[i]:
            email = None
        elif from_online[i]:
            email = str(rng.choice(online_emails))
        else:
            email = str(pool[pool_position])
            pool_position += 1
        rows.append(
            {
                "customer_email": email,
                "channel": "offline",
                "country_code": "JP",
                "ordered_at": timestamps[i],
            }
        )
    return rows


def build_fx_table(rng, config, days):
    drift = config["fx_monthly_drift"]
    months = sorted({(day.year, day.month) for day in days})
    table = {}
    for currency, base_rate in config["fx_to_jpy"].items():
        for month in months:
            if currency == "JPY":
                table[(currency, month)] = 1.0
            else:
                table[(currency, month)] = round(base_rate * (1 + rng.normal(0, drift)), 6)
    return table


def stock_band(price, bands):
    for band in bands:
        if price <= band["max_price"]:
            return band["low"], band["high"]
    return bands[-1]["low"], bands[-1]["high"]


def close_week(rng, config, bands, skus, stock, boundary, apply_restock, snapshots):
    if apply_restock:
        threshold = config["inventory"]["restock_when_at_or_below"]
        probability = config["inventory"]["restock_probability"]
        for index in np.where(stock <= threshold)[0]:
            if rng.random() < probability:
                low, high = bands[index]
                stock[index] += rng.integers(low, high + 1)
    snapshot_date = boundary.date().isoformat()
    for sku, quantity in zip(skus, stock):
        snapshots.append(
            {
                "sku": str(sku),
                "snapshot_date": snapshot_date,
                "quantity_on_hand": int(quantity),
                "data_source": DATA_SOURCE,
            }
        )


def pick_status(rng, config, ordered_at, end):
    settings = config["status"]
    roll = rng.random()
    if roll < settings["cancelled"]:
        return "cancelled"
    if roll < settings["cancelled"] + settings["refunded"]:
        return "refunded"
    window = pd.Timedelta(days=settings["paid_window_days"])
    if ordered_at > end + pd.Timedelta(days=1) - window:
        return "paid"
    return "fulfilled"


def simulate(rng, config, products, skeleton, fx_table):
    start, end = period_bounds(config)
    skus = products["sku"].to_numpy()
    prices = products["price_jpy"].to_numpy()
    basket = config["basket"]

    popularity = rng.lognormal(0.0, basket["popularity_sigma"], size=len(products))
    price_factor = (prices / np.median(prices)) ** (-basket["price_penalty_exponent"])
    base_weights = popularity * price_factor

    bands = [stock_band(price, config["inventory"]["start_stock_by_price"]) for price in prices]
    stock = np.array([rng.integers(low, high + 1) for low, high in bands])

    orders, items, snapshots = [], [], []
    boundary = start

    for order in skeleton:
        while boundary <= order["ordered_at"]:
            close_week(rng, config, bands, skus, stock, boundary, boundary != start, snapshots)
            boundary += ONE_WEEK

        available = stock > 0
        if not available.any():
            continue

        status = pick_status(rng, config, order["ordered_at"], end)
        wanted = int(weighted_choice(rng, basket["items_per_order"]))
        count = min(wanted, int(available.sum()))
        weights = base_weights * available
        chosen = rng.choice(len(skus), size=count, replace=False, p=weights / weights.sum())

        total_jpy = 0
        for index in chosen:
            quantity = 2 if rng.random() < basket["quantity_two_share"] else 1
            quantity = min(quantity, int(stock[index]))
            if status != "cancelled":
                stock[index] -= quantity
            unit_price = int(prices[index])
            total_jpy += quantity * unit_price
            items.append(
                {
                    "order_number": order["order_number"],
                    "sku": str(skus[index]),
                    "quantity": quantity,
                    "unit_price_jpy": unit_price,
                }
            )

        currency = config["country_currency"][order["country_code"]]
        month = (order["ordered_at"].year, order["ordered_at"].month)
        fx_rate = fx_table[(currency, month)]
        orders.append(
            {
                "order_number": order["order_number"],
                "data_source": DATA_SOURCE,
                "customer_email": order["customer_email"],
                "channel": order["channel"],
                "country_code": order["country_code"],
                "status": status,
                "currency": currency,
                "fx_rate_to_jpy": fx_rate,
                "amount_original": round(total_jpy / fx_rate, 2),
                "amount_jpy": total_jpy,
                "ordered_at": order["ordered_at"],
            }
        )

    while boundary <= end:
        close_week(rng, config, bands, skus, stock, boundary, True, snapshots)
        boundary += ONE_WEEK
    if boundary - ONE_WEEK != end:
        close_week(rng, config, bands, skus, stock, end, False, snapshots)

    return orders, items, snapshots


def print_summary(customers, orders, items, snapshots, products):
    print("customers:", len(customers))
    print("orders:", len(orders))
    print("order items:", len(items))
    print("inventory rows:", len(snapshots))
    print()
    print("order share by channel:")
    print(orders["channel"].value_counts(normalize=True).round(3).to_string())
    online = orders[orders["channel"] == "online"]
    print()
    print("top online countries (share of online orders):")
    print(online["country_code"].value_counts(normalize=True).head(5).round(3).to_string())
    per_customer = online.groupby("customer_email").size()
    print()
    print("online customers with more than one online order:", round((per_customer > 1).mean(), 3))
    offline = orders[orders["channel"] == "offline"]
    print("offline orders without a customer:", round(offline["customer_email"].isna().mean(), 3))
    print()
    print("status share:")
    print(orders["status"].value_counts(normalize=True).round(3).to_string())
    print()
    print("busiest months (orders):")
    print(orders["ordered_at"].str[:7].value_counts().head(4).to_string())
    print()
    sold = set(items["sku"])
    print("products never sold:", len(set(products["sku"]) - sold))
    print("share of inventory rows at zero stock:", round((snapshots["quantity_on_hand"] == 0).mean(), 3))


def main():
    config = load_config()
    rng = np.random.default_rng(config["seed"])
    Faker.seed(config["seed"])
    fake = Faker("en_US")

    products = pd.read_csv(PRODUCTS_PATH)
    calendar = build_calendar(config)
    customers = build_customers(rng, fake, config)

    skeleton = build_online_orders(rng, config, calendar, customers)
    skeleton += build_offline_orders(rng, config, calendar, customers)
    skeleton.sort(key=lambda order: order["ordered_at"])
    for number, order in enumerate(skeleton, start=1):
        order["order_number"] = f"SYN-{number:05d}"

    fx_table = build_fx_table(rng, config, calendar[0])
    orders, items, snapshots = simulate(rng, config, products, skeleton, fx_table)

    orders = pd.DataFrame(orders)
    items = pd.DataFrame(items)
    snapshots = pd.DataFrame(snapshots)

    first_order = (
        orders.dropna(subset=["customer_email"])
        .groupby("customer_email")["ordered_at"]
        .min()
        .rename("created_at")
    )
    customers = customers.merge(first_order, left_on="email", right_index=True, how="inner")
    customers["data_source"] = DATA_SOURCE

    time_format = "%Y-%m-%dT%H:%M:%S+00:00"
    orders["ordered_at"] = orders["ordered_at"].dt.strftime(time_format)
    customers["created_at"] = customers["created_at"].dt.strftime(time_format)
    customers = customers[
        ["email", "first_name", "last_name", "country_code", "created_at", "data_source"]
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    customers.to_csv(OUTPUT_DIR / "customers.csv", index=False, encoding="utf-8")
    orders.to_csv(OUTPUT_DIR / "orders.csv", index=False, encoding="utf-8")
    items.to_csv(OUTPUT_DIR / "order_items.csv", index=False, encoding="utf-8")
    snapshots.to_csv(OUTPUT_DIR / "inventory_snapshots.csv", index=False, encoding="utf-8")

    print_summary(customers, orders, items, snapshots, products)


if __name__ == "__main__":
    main()