#!/usr/bin/env bash
# Production-first Frappe boot: apps/assets are baked in the image.
# Runtime work is limited to DB wait, site bootstrap, optional migrate, and process start.
set -euo pipefail

export PYENV_ROOT="${PYENV_ROOT:-/home/frappe/.pyenv}"
export PATH="${PYENV_ROOT}/shims:${PYENV_ROOT}/bin:/home/frappe/.local/bin:${PATH}"
export NVM_DIR="${NVM_DIR:-/home/frappe/.nvm}"
# shellcheck disable=SC1091
[ -s "${NVM_DIR}/nvm.sh" ] && . "${NVM_DIR}/nvm.sh"

BENCH_DIR="${BENCH_DIR:-/home/frappe/frappe-bench}"
SITE="${SITE_NAME:-localhost}"
DB_HOST="${DB_HOST:-mariadb}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
FRAPPE_ENV="${FRAPPE_ENV:-production}"
MIGRATE_ON_START="${MIGRATE_ON_START:-1}"
SEED_DEMO_DATA="${SEED_DEMO_DATA:-0}"
BUILD_ASSETS_ON_START="${BUILD_ASSETS_ON_START:-0}"
DEVELOPER_MODE="${DEVELOPER_MODE:-}"

CMD="${1:-start}"

wait_for_db() {
	echo "[bench] waiting for MariaDB at ${DB_HOST}..."
	for _ in $(seq 1 60); do
		if mysqladmin ping -h "${DB_HOST}" -uroot -p"${DB_ROOT_PASSWORD}" --silent 2>/dev/null; then
			return 0
		fi
		sleep 3
	done
	mysqladmin ping -h "${DB_HOST}" -uroot -p"${DB_ROOT_PASSWORD}" --silent
}

is_development() {
	[ "${FRAPPE_ENV}" = "development" ]
}

developer_mode_value() {
	if [ -n "${DEVELOPER_MODE}" ]; then
		echo "${DEVELOPER_MODE}"
	elif is_development; then
		echo "1"
	else
		echo "0"
	fi
}

configure_bench() {
	cd "${BENCH_DIR}"
	bench set-config -g db_host "${DB_HOST}"
	bench set-config -gp db_port 3306
	bench set-config -g redis_cache "redis://redis-cache:6379"
	bench set-config -g redis_queue "redis://redis-queue:6379"
	bench set-config -g redis_socketio "redis://redis-queue:6379"
	bench set-config -gp socketio_port 9000
	bench set-config -g developer_mode "$(developer_mode_value)"
	bench set-config -g default_site "${SITE}"
}

ensure_site() {
	cd "${BENCH_DIR}"
	if [ -d "sites/${SITE}" ]; then
		return 0
	fi

	echo "[bench] creating site ${SITE}"
	bench new-site "${SITE}" \
		--mariadb-user-host-login-scope='%' \
		--admin-password="${ADMIN_PASSWORD}" \
		--db-root-username=root \
		--db-root-password="${DB_ROOT_PASSWORD}" \
		--set-default
	bench --site "${SITE}" install-app hr_portal
	bench --site "${SITE}" install-app crm
}

maybe_migrate() {
	if [ "${MIGRATE_ON_START}" != "1" ]; then
		echo "[bench] skipping migrate (MIGRATE_ON_START=${MIGRATE_ON_START})"
		return 0
	fi
	echo "[bench] migrate ${SITE}"
	bench --site "${SITE}" migrate
}

configure_site() {
	cd "${BENCH_DIR}"
	echo "${SITE}" > sites/currentsite.txt
	bench use "${SITE}" || true

	local host="${SITE_HOSTNAME:-http://localhost:8000}"
	bench --site "${SITE}" set-config hostname "${host}"
	bench --site "${SITE}" set-config developer_mode "$(developer_mode_value)"

	if is_development; then
		bench --site "${SITE}" set-config ignore_csrf 1
		bench --site "${SITE}" set-config allow_cors "*"
		if [ -z "${MAIL_HOST:-}" ]; then
			bench --site "${SITE}" set-config mail_server mailpit
			bench --site "${SITE}" set-config mail_port 1025
		fi
	else
		bench --site "${SITE}" set-config ignore_csrf 0
		if [ -n "${ALLOW_CORS:-}" ]; then
			bench --site "${SITE}" set-config allow_cors "${ALLOW_CORS}"
		fi
	fi

	if [ -n "${MAIL_HOST:-}" ]; then
		bench --site "${SITE}" set-config mail_server "${MAIL_HOST}"
		bench --site "${SITE}" set-config mail_port "${MAIL_PORT:-587}"
	fi
}

maybe_seed_demo_data() {
	if [ "${SEED_DEMO_DATA}" != "1" ]; then
		return 0
	fi
	echo "[bench] seeding demo users (SEED_DEMO_DATA=1)"
	bench --site "${SITE}" execute hr_portal.docker_setup.ensure_dev_users
}

dev_reinstall_hr_portal() {
	if ! is_development; then
		return 0
	fi
	if [ ! -f apps/hr_portal/pyproject.toml ]; then
		return 0
	fi
	echo "[bench] development: refreshing hr_portal python package"
	./env/bin/pip install -q -e apps/hr_portal
}

build_assets_if_requested() {
	if [ "${BUILD_ASSETS_ON_START}" != "1" ]; then
		return 0
	fi
	echo "[bench] BUILD_ASSETS_ON_START=1 — rebuilding frontends"
	if [ -d apps/hr_portal/frontend ]; then
		(
			cd apps/hr_portal/frontend
			yarn install --frozen-lockfile 2>/dev/null || yarn install
			yarn build
		)
	fi
	if [ -d apps/crm/frontend ]; then
		(
			cd apps/crm/frontend
			yarn install --frozen-lockfile 2>/dev/null || yarn install
			yarn build
		)
	fi
}

print_urls() {
	echo "[bench] ready"
	echo "  Desk  ${SITE_HOSTNAME:-http://localhost:8000}       Administrator / ${ADMIN_PASSWORD}"
	if [ "${SEED_DEMO_DATA}" = "1" ]; then
		echo "  HR    ${SITE_HOSTNAME:-http://localhost:8000}/hr    hr.admin@example.com / admin"
	fi
	echo "  CRM   ${SITE_HOSTNAME:-http://localhost:8000}/crm   Administrator / ${ADMIN_PASSWORD}"
}

run_migrate_only() {
	wait_for_db
	configure_bench
	ensure_site
	maybe_migrate
	bench --site "${SITE}" clear-cache
}

run_start() {
	wait_for_db
	configure_bench
	dev_reinstall_hr_portal
	ensure_site
	maybe_migrate
	configure_site
	maybe_seed_demo_data
	build_assets_if_requested
	bench --site "${SITE}" clear-cache
	print_urls
	exec bench start
}

case "${CMD}" in
	start)
		run_start
		;;
	migrate)
		run_migrate_only
		;;
	*)
		exec "$@"
		;;
esac
