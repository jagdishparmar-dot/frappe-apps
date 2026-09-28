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

# Site still lists an app that is no longer in the image (apps/ folder removed
# without uninstall-app). bench uninstall-app / migrate both import the Python
# package, so they fail with ModuleNotFoundError and Coolify never finishes.
# Drop the name from apps.txt + MariaDB without importing the missing module.
# DocType tables are left in place (safe leftover); they are not dropped.
unregister_missing_apps() {
  local site="$1"
  [[ -d "sites/${site}" && -f "sites/${site}/site_config.json" ]] || return 0

  echo "Checking ${site} for installed apps missing from this image..."
  ./env/bin/python - "${site}" <<'PY'
import json
import sys
from pathlib import Path

site = sys.argv[1]
bench = Path("/home/frappe/frappe-bench")
available = {p.name for p in (bench / "apps").iterdir() if p.is_dir()}
available.add("frappe")

apps_txt = bench / "sites" / site / "apps.txt"
site_cfg = json.loads((bench / "sites" / site / "site_config.json").read_text())
common = json.loads((bench / "sites" / "common_site_config.json").read_text())

installed = []
if apps_txt.is_file():
    installed = [line.strip() for line in apps_txt.read_text().splitlines() if line.strip()]

import pymysql

conn = pymysql.connect(
    host=str(common.get("db_host") or "db"),
    port=int(common.get("db_port") or 3306),
    user=str(site_cfg.get("db_user") or site_cfg["db_name"]),
    password=str(site_cfg["db_password"]),
    database=str(site_cfg["db_name"]),
    charset="utf8mb4",
    autocommit=False,
)
cur = conn.cursor()
cur.execute("SELECT defvalue FROM `tabDefaultValue` WHERE defkey=%s", ("installed_apps",))
for (defvalue,) in cur.fetchall():
    if not defvalue:
        continue
    try:
        db_apps = json.loads(defvalue)
    except (TypeError, json.JSONDecodeError):
        continue
    if isinstance(db_apps, list) and db_apps:
        installed = db_apps
        break

missing = [app for app in installed if app and app not in available]
if not missing:
    print(f"  {site}: all installed apps are present in the image")
    conn.close()
    sys.exit(0)

kept = [app for app in installed if app in available]
print(f"  {site}: unregistering missing apps (tables kept): {', '.join(missing)}")

cur.execute(
    "UPDATE `tabDefaultValue` SET defvalue=%s WHERE defkey=%s",
    (json.dumps(kept), "installed_apps"),
)

cur.execute("SHOW TABLES LIKE 'tabInstalled Application'")
if cur.fetchone():
    for app in missing:
        cur.execute("DELETE FROM `tabInstalled Application` WHERE app_name=%s", (app,))

conn.commit()
conn.close()
apps_txt.write_text("\n".join(kept) + ("\n" if kept else ""))

try:
    import redis

    url = common.get("redis_cache")
    if url:
        redis.from_url(str(url)).flushdb()
        print(f"  {site}: flushed redis-cache after unregister")
except Exception as exc:
    print(f"  {site}: warning — could not flush redis-cache: {exc}")
PY
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
    unregister_missing_apps "${site}"
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
