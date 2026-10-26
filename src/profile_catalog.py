import pandas as pd

df = pd.read_csv("data/raw/catalog_raw.csv")

print("rows:", len(df))
print("duplicate handles:", df["handle"].duplicated().sum())
print("missing price:", df["price"].isna().sum())
print("price zero or less:", (df["price"] <= 0).sum())
print("products with more than 1 variant:", (df["variant_count"] > 1).sum())
print()
print(df["price"].describe())
print()
print(df["vendor"].value_counts().to_string())