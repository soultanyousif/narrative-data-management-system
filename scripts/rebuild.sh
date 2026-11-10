#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
source .env
set +a

step() { echo "== $1"; }
main_sql() { docker compose exec -T db psql -U "$POSTGRES_USER" -d narrative_dw -v ON_ERROR_STOP=1 "$@"; }
test_sql() { docker compose exec -T db psql -U "$POSTGRES_USER" -d narrative_test -v ON_ERROR_STOP=1 "$@"; }

step "Start containers"
docker compose up -d --wait

step "Python environment"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install --quiet -r requirements.txt

for file in 001_schema.sql 002_inventory_source.sql 003_shopify_alignment.sql 004_reporting_views.sql; do
  step "Apply $file"
  main_sql < "sql/$file"
done

step "Create read-only reporting user"
main_sql -v reader_password="$METABASE_READER_PASSWORD" < sql/005_reporting_access.sql

step "Create test database"
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 < sql/admin/create_test_db.sql

for file in 001_schema.sql 002_inventory_source.sql 003_shopify_alignment.sql 004_reporting_views.sql; do
  step "Test database: $file"
  test_sql < "sql/$file"
done

step "Generate synthetic data"
python src/generate_synthetic.py
step "Load products"
python src/load_products.py
step "Load synthetic data"
python src/load_synthetic.py
step "Run integrity checks"
python src/check_data.py
step "Run automated tests"
python -m pytest -q

echo "Done."