# Narrative Platform customer and sales data system

A prototype that centralises customer, order and inventory data for Narrative Platform
and shows it in one dashboard. It runs on synthetic data and the public product catalog.
No private MONOUN data is stored in this repository.

Status: Week 2 of 4 complete. Done: database, product catalog, synthetic data,
Shopify import, offline sales template and import, automated tests, dashboard preview.
Next (Week 3): reporting layer and the five-page dashboard.

## Requirements
Docker Desktop, Python 3.13, Git. Commands below are for Windows PowerShell.

## Setup
1. Copy .env.example to .env and set a password.
2. Create and activate a Python environment, then install packages:
       python -m venv .venv
       .venv\Scripts\Activate.ps1
       pip install -r requirements.txt
3. Build everything with one command (containers, schema, test database, data, checks, tests):
       .\scripts\rebuild.ps1
4. Open Metabase at http://localhost:3000 and connect it to PostgreSQL
   (host db, port 5432, database narrative_dw, user and password from .env).

## Repository layout
- docker-compose.yml: PostgreSQL 16 and Metabase v0.64.1
- sql/: schema files, applied in numbered order (001, 002, 003); sql/admin creates the test database
- src/: catalog collection, synthetic data, loaders, integrity checks
- config/synthetic.yaml: every assumption behind the synthetic data
- config/shopify_mapping.yaml: the approved list of Shopify columns and the status mapping
- data/raw, data/seed: public catalog files (854 products)
- data/fixtures: fake export files used for testing
- templates/offline_sales_template.xlsx: Excel template for offline sales
- tests/: automated tests and generators for the fake files
- docs/metrics.md: definitions of every dashboard metric
- docs/shopify_headers.md: column names of the Shopify exports (names only)

## Data layers
- staging: batch log (etl_batches) and rejected rows with the reason (rejected_rows)
- core: customers, products, orders, order_items, inventory_snapshots
- reporting: views that the dashboard reads (Week 3)

Every customer, order and stock row carries a data_source value (synthetic, offline_csv,
shopify_csv), so synthetic and real data can never be confused.

## Loading data
Shopify exports (customers first, then orders):
    python src\shopify_loader.py --customers <Customers.csv> --orders <Orders.csv>

Offline sales (the Excel template):
    python src\offline_loader.py --file <filled_template.xlsx>

How loading works:
- Only the columns listed in config/shopify_mapping.yaml are read. Names, phone numbers,
  addresses, IP addresses and payment fields are never read.
- Rows of one order are grouped by the real order ID. Shipping rows are kept out of revenue.
- An order that does not add up, or contains an unknown product, status or source,
  is rejected as a whole and written to staging.rejected_rows with the reason.
- Loads are repeatable: running the same file again changes nothing.
- Real exports must stay in data/private, which Git ignores. Never commit real customer data.

## Tests and checks
    python -m pytest -q          automated tests, run on the separate narrative_test database
    python src\check_data.py     13 data quality checks on the main database
Tests refuse to run on any database whose name does not end in _test.
To point a script at the test database: $env:TARGET_DB = "narrative_test"

## Moving from synthetic to real data
1. Dry run on a small anonymised export. Only the column mapping should need changes.
2. Parallel run: compare dashboard totals with Shopify's own reports.
3. Go live under MONOUN's permissions, with every row labelled by data_source.

## Assumptions (to confirm with MONOUN)
Seen in the sample export:
- Prices include the 10% consumption tax.
- One order spans several rows (items, shipping, payment); rows are grouped by order ID.
- Products have no SKU in the store; they are matched by product handle.

Still assumptions:
- Revenue excludes shipping and cancelled orders. A full refund removes the order from
  revenue; a partial refund keeps the order and is subtracted from revenue.
- Products with several variants (4 of 854) are one row, priced by the first variant.
- A product listed in several shop categories gets the lowest-numbered category (42 products).
- Makers come from the shop's maker, artist and brand collections (73 products unspecified).
- Jewelry exists as a category but has no products today.
- Generated SKUs (NP-0001 and up) exist only for the catalog; real data is matched by product_url.
- Offline sales are recorded as Japan and yen, at 12:00 Tokyo time on the sale date.
- All synthetic volumes and rates are assumptions, not MONOUN figures.

## Open questions for MONOUN
1. Do physical-store sales go through Shopify (register), or are they recorded elsewhere?
2. Products export with inventory quantity (column names only), for real stock levels.