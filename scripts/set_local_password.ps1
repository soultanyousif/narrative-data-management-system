$password = Read-Host "Choose one password for the local system (letters and numbers only, 12 or more characters)"
if ($password -notmatch '^[A-Za-z0-9]{12,}$') { throw "Use only letters and numbers, at least 12 characters" }

docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { throw "Could not start the database container" }

docker compose exec db psql -U narrative -d postgres -c "ALTER ROLE narrative PASSWORD '$password';"
if ($LASTEXITCODE -ne 0) { throw "Could not change the database password" }

$lines = @(
    "POSTGRES_USER=narrative",
    "POSTGRES_PASSWORD=$password",
    "POSTGRES_DB=narrative_dw",
    "METABASE_READER_PASSWORD=$password",
    "METABASE_URL=http://localhost:3000",
    "METABASE_ADMIN_EMAIL=soultanyousif@outlook.com",
    "METABASE_ADMIN_PASSWORD=$password"
)
Set-Content -Path .env -Value $lines -Encoding ascii
Write-Host "Done. .env now uses your password everywhere."