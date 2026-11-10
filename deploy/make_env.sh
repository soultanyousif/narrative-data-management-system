#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

read -r -p "Server IP address (for example 203.0.113.10): " IP
read -r -s -p "Choose ONE password for the server (letters and numbers only, 16 or more): " PW
echo
if ! [[ "$PW" =~ ^[A-Za-z0-9]{16,}$ ]]; then
  echo "Use only letters and numbers, at least 16 characters"
  exit 1
fi
HOST="${IP//./-}.sslip.io"

cat > .env <<EOF
POSTGRES_USER=narrative
POSTGRES_PASSWORD=$PW
POSTGRES_DB=narrative_dw
METABASE_READER_PASSWORD=$PW
METABASE_URL=https://$HOST
METABASE_ADMIN_EMAIL=soultanyousif@outlook.com
METABASE_ADMIN_PASSWORD=$PW
SITE_ADDRESS=$HOST
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
EOF
chmod 600 .env
echo ".env written. Your dashboard address will be https://$HOST"