$ErrorActionPreference = "Stop"

function Step($label, [scriptblock]$command) {
    Write-Host "== $label"
    & $command
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $label" }
}

Step "Start containers" { docker compose up -d --wait }
Step "Apply schema" { Get-Content sql\001_schema.sql | docker compose exec -T db psql -U narrative -d narrative_dw -v ON_ERROR_STOP=1 }
Step "Apply inventory source update" { Get-Content sql\002_inventory_source.sql | docker compose exec -T db psql -U narrative -d narrative_dw -v ON_ERROR_STOP=1 }
Step "Apply Shopify alignment" { Get-Content sql\003_shopify_alignment.sql | docker compose exec -T db psql -U narrative -d narrative_dw -v ON_ERROR_STOP=1 }
Step "Create test database" { Get-Content sql\admin\create_test_db.sql | docker compose exec -T db psql -U narrative -d postgres -v ON_ERROR_STOP=1 }
foreach ($file in "001_schema.sql", "002_inventory_source.sql", "003_shopify_alignment.sql") {
    Step "Test database: $file" { Get-Content "sql\$file" | docker compose exec -T db psql -U narrative -d narrative_test -v ON_ERROR_STOP=1 }
}
Step "Generate synthetic data" { python src\generate_synthetic.py }
Step "Load products" { python src\load_products.py }
Step "Load synthetic data" { python src\load_synthetic.py }
Step "Run integrity checks" { python src\check_data.py }

Step "Run automated tests" { python -m pytest -q }
Write-Host "Done. Metabase: http://localhost:3000"