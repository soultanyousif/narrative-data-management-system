# Narrative Platform customer and sales data system

A prototype for centralising customer, order and inventory data for Narrative Platform.
Built on synthetic data and the public product catalog.

Status: Week 1 of 4 complete (database, catalog, synthetic data, integrity checks).

## What is in the repository
- docker-compose.yml: PostgreSQL 16 and Metabase v0.64.1
- sql/: database schema (core tables) and later changes, applied in numbered order
- src/: catalog collection, synthetic data generation, loaders, integrity checks
- config/synthetic.yaml: all assumptions for synthetic data (volumes, countries, seasonality, stock)
- data/raw/: public catalog files as downloaded
- data/seed/products.csv: the cleaned product catalog (854 products)
- docs/metrics.md: definitions of every dashboard metric

## Requirements
Docker Desktop, Python 3.13, Git.

## Setup
1. Copy .env.example to .env and set a password.
2. Create and activate a Python environment, then install packages:
       python -m venv .venv
       .venv\Scripts\Activate.ps1
       pip install -r requirements.txt
3. Build everything with one command:
       .\scripts\rebuild.ps1
4. Open Metabase at http://localhost:3000

## Data layers
- staging: raw incoming files (added in Week 2)
- core: clean business tables (customers, products, orders, order_items, inventory_snapshots)
- reporting: views that the dashboard reads (added in Week 3)

Every customer, order and stock row carries a data_source value (synthetic, offline_csv,
shopify_csv) so synthetic and real data can never be confused.

## Moving from synthetic to real data
1. Dry run on a small export or anonymised sample.
2. Parallel run: compare totals with Shopify's own reports.
3. Go live under MONOUN's permissions.

## Assumptions made without MONOUN input (to confirm)
- Revenue is tax-inclusive, excludes shipping, and excludes cancelled and refunded orders.
- Products with several variants (4 of 854) are one row, priced by the first variant.
- A product in several shop categories gets the category with the lowest number (42 products).
- Makers come from the shop's maker, artist and brand collections (73 products unspecified).
- Jewelry exists as a category but has no products today.
- SKUs are generated (NP-0001 and up) because the store has no SKUs. Real data should be
  matched by product_url.
- All synthetic volumes and rates are assumptions, not MONOUN figures.
