#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${SITE_NAME:-vendors.localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
DB_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-admin}"
# Public origin used by Frappe behind Coolify / reverse proxy, e.g. https://desk.example.com
SITE_HOST_NAME="${SITE_HOST_NAME:-}"
# Install Frappe CRM on the site when the app is present in the image (default: yes)
INSTALL_CRM="${INSTALL_CRM:-1}"
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

install_apps=(vendor_directory)
if [[ "${INSTALL_CRM}" == "1" && -d "apps/crm" ]]; then
  install_apps+=(crm)
elif [[ "${INSTALL_CRM}" == "1" ]]; then
  echo "WARNING: INSTALL_CRM=1 but apps/crm is missing from the image — rebuild with INSTALL_CRM=1"
fi

install_app_flags=()
for app in "${install_apps[@]}"; do
  install_app_flags+=(--install-app "${app}")
done

ensure_apps_installed() {
  for app in "${install_apps[@]}"; do
    echo "Ensuring app installed: ${app}"
    bench --site "${SITE_NAME}" install-app "${app}" || true
  done
  bench --site "${SITE_NAME}" migrate
}

if [[ -d "sites/${SITE_NAME}" ]]; then
  echo "Site ${SITE_NAME} already exists — ensuring apps are installed"
  ensure_apps_installed
else
  echo "Creating site ${SITE_NAME} with apps: ${install_apps[*]}"
  bench new-site "${SITE_NAME}" \
    --mariadb-user-host-login-scope='%' \
    --admin-password="${ADMIN_PASSWORD}" \
    --db-root-username=root \
    --db-root-password="${DB_ROOT_PASSWORD}" \
    "${install_app_flags[@]}" \
    --set-default
fi

# Behind Coolify / Traefik / Caddy: tell Frappe its public HTTPS URL
# Skip incomplete values like "https://" which Coolify/env UIs sometimes leave blank.
if [[ -n "${SITE_HOST_NAME}" && "${SITE_HOST_NAME}" != "https://" && "${SITE_HOST_NAME}" != "http://" ]]; then
  if [[ "${SITE_HOST_NAME}" =~ ^https?://[^/]+ ]]; then
    echo "Setting host_name=${SITE_HOST_NAME}"
    bench --site "${SITE_NAME}" set-config host_name "${SITE_HOST_NAME}"
  else
    echo "Skipping invalid SITE_HOST_NAME=${SITE_HOST_NAME} (expected e.g. https://desk.example.com)"
  fi
fi

echo "Writing optional API credentials file (not required for UI login)"
bench --site "${SITE_NAME}" execute vendor_directory.bootstrap.write_api_credentials \
  --kwargs "{\"path\": \"${CREDENTIALS_FILE}\"}" || echo "Skipped API credential write"

echo "Site bootstrap complete (apps: ${install_apps[*]})"
