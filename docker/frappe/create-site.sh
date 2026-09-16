#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${SITE_NAME:-vendors.localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
DB_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-admin}"
SITE_HOST_NAME="${SITE_HOST_NAME:-}"
INSTALL_APPS="${INSTALL_APPS:-}"
SKIP_INSTALL_APPS="${SKIP_INSTALL_APPS:-}"
CONTROL_SITE_NAME="${CONTROL_SITE_NAME:-}"
CONTROL_SITE_APPS="${CONTROL_SITE_APPS:-bench_control}"

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

all_apps=()
for app in $(ls -1 apps); do
  [[ "${app}" == "frappe" ]] && continue
  all_apps+=("${app}")
done
if [[ ${#all_apps[@]} -eq 0 ]]; then
  echo "WARNING: no apps found in the image — expected at least one under apps/"
fi

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

is_skipped() {
  local needle="$1"
  local item
  local IFS=','
  for item in ${SKIP_INSTALL_APPS}; do
    item="$(trim "${item}")"
    [[ -n "${item}" && "${item}" == "${needle}" ]] && return 0
  done
  return 1
}

# Populate nameref array with resolved app names
resolve_apps_into() {
  local -n _out="$1"
  local requested="$2"
  local item app
  _out=()
  if [[ -z "${requested}" ]]; then
    for app in "${all_apps[@]}"; do
      is_skipped "${app}" && continue
      _out+=("${app}")
    done
    return 0
  fi
  local IFS=','
  for item in ${requested}; do
    item="$(trim "${item}")"
    [[ -z "${item}" ]] && continue
    if [[ ! -d "apps/${item}" ]]; then
      echo "WARNING: requested app '${item}' not in image — skipping"
      continue
    fi
    _out+=("${item}")
  done
}

ensure_site() {
  local site="$1"
  shift
  local apps=("$@")
  local flags=()
  local app
  local set_default_flag=()

  # Only the primary SITE_NAME becomes default on first create
  if [[ "${site}" == "${SITE_NAME}" ]]; then
    set_default_flag=(--set-default)
  fi

  for app in "${apps[@]+"${apps[@]}"}"; do
    flags+=(--install-app "${app}")
  done

  if [[ -d "sites/${site}" ]]; then
    echo "Site ${site} already exists — ensuring apps: ${apps[*]:-none}"
    for app in "${apps[@]+"${apps[@]}"}"; do
      echo "Ensuring app installed: ${app}"
      bench --site "${site}" install-app "${app}" || true
    done
    bench --site "${site}" migrate
  else
    echo "Creating site ${site} with apps: ${apps[*]:-none}"
    bench new-site "${site}" \
      --mariadb-user-host-login-scope='%' \
      --admin-password="${ADMIN_PASSWORD}" \
      --db-root-username=root \
      --db-root-password="${DB_ROOT_PASSWORD}" \
      "${flags[@]+"${flags[@]}"}" \
      "${set_default_flag[@]+"${set_default_flag[@]}"}"
  fi
}

primary_apps=()
resolve_apps_into primary_apps "${INSTALL_APPS}"
ensure_site "${SITE_NAME}" "${primary_apps[@]+"${primary_apps[@]}"}"

if [[ -n "${CONTROL_SITE_NAME}" && "${CONTROL_SITE_NAME}" != "${SITE_NAME}" ]]; then
  control_apps=()
  resolve_apps_into control_apps "${CONTROL_SITE_APPS}"
  ensure_site "${CONTROL_SITE_NAME}" "${control_apps[@]+"${control_apps[@]}"}"
fi

if [[ -n "${SITE_HOST_NAME}" && "${SITE_HOST_NAME}" != "https://" && "${SITE_HOST_NAME}" != "http://" ]]; then
  if [[ "${SITE_HOST_NAME}" =~ ^https?://[^/]+ ]]; then
    echo "Setting host_name=${SITE_HOST_NAME}"
    bench --site "${SITE_NAME}" set-config host_name "${SITE_HOST_NAME}"
  else
    echo "Skipping invalid SITE_HOST_NAME=${SITE_HOST_NAME} (expected e.g. https://desk.example.com)"
  fi
fi

echo "Site bootstrap complete (primary=${SITE_NAME} apps=${primary_apps[*]:-none})"
