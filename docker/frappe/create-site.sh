#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${SITE_NAME:-vendors.localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
DB_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-admin}"
# Public origin used by Frappe behind Coolify / reverse proxy, e.g. https://desk.example.com
SITE_HOST_NAME="${SITE_HOST_NAME:-}"
# Write into the sites volume (owned by frappe). The anonymous /shared volume is root-owned.
CREDENTIALS_FILE="${CREDENTIALS_FILE:-/home/frappe/frappe-bench/sites/credentials.json}"

mkdir -p /home/frappe/frappe-bench/logs
cd /home/frappe/frappe-bench

wait-for-it -t 120 db:3306
wait-for-it -t 120 redis-cache:6379
wait-for-it -t 120 redis-queue:6379

start="$(date +%s)"
until [[ -n "$(grep -hs ^ sites/common_site_config.json | jq -r '.db_host // empty')" ]] \
  && [[ -n "$(grep -hs ^ sites/common_site_config.json | jq -r '.redis_cache // empty')" ]] \
  && [[ -n "$(grep -hs ^ sites/common_site_config.json | jq -r '.redis_queue // empty')" ]]; do
  echo "Waiting for sites/common_site_config.json..."
  sleep 5
  if (( "$(date +%s)" - start > 180 )); then
    echo "Timed out waiting for common_site_config.json"
    exit 1
  fi
done

echo "common_site_config.json ready"

if [[ -d "sites/${SITE_NAME}" ]]; then
  echo "Site ${SITE_NAME} already exists — ensuring vendor_directory is installed"
  bench --site "${SITE_NAME}" install-app vendor_directory || true
  bench --site "${SITE_NAME}" migrate
else
  echo "Creating site ${SITE_NAME} (Frappe + vendor_directory only)"
  bench new-site "${SITE_NAME}" \
    --mariadb-user-host-login-scope='%' \
    --admin-password="${ADMIN_PASSWORD}" \
    --db-root-username=root \
    --db-root-password="${DB_ROOT_PASSWORD}" \
    --install-app vendor_directory \
    --set-default
fi

# Behind Coolify / Traefik / Caddy: tell Frappe its public HTTPS URL
if [[ -n "${SITE_HOST_NAME}" ]]; then
  echo "Setting host_name=${SITE_HOST_NAME}"
  bench --site "${SITE_NAME}" set-config host_name "${SITE_HOST_NAME}"
fi

echo "Writing optional API credentials file (not required for UI login)"
bench --site "${SITE_NAME}" execute vendor_directory.bootstrap.write_api_credentials \
  --kwargs "{\"path\": \"${CREDENTIALS_FILE}\"}" || echo "Skipped API credential write"

echo "Site bootstrap complete"
