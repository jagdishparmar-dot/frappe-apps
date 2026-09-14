#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${SITE_NAME:-vendors.localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
DB_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-admin}"
# Public origin used by Frappe behind Coolify / reverse proxy, e.g. https://desk.example.com
SITE_HOST_NAME="${SITE_HOST_NAME:-}"

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

# Install every app baked into the image (apps/ folder in the build context).
# Adding an app = adding its folder to apps/ at build time — no changes needed here.
install_apps=()
for app in $(ls -1 apps); do
  [[ "${app}" == "frappe" ]] && continue
  install_apps+=("${app}")
done
if [[ ${#install_apps[@]} -eq 0 ]]; then
  echo "WARNING: no apps found in the image — expected at least one under apps/"
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

echo "Site bootstrap complete (apps: ${install_apps[*]})"
