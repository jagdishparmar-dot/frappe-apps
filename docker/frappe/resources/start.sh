#!/bin/bash
set -e

# ── Gunicorn configuration ───────────────────────────────────────────────────
# nproc on Coolify reports HOST cores, not this container's cgroup quota.
# Using 2×nproc+1 on a shared 8-core box would start 17 workers and OOM.
# Prefer the cgroup quota; cap the auto formula so neighbours stay safe.

detect_cpu_quota() {
  local quota period cores
  if [ -r /sys/fs/cgroup/cpu.max ]; then
    read -r quota period < /sys/fs/cgroup/cpu.max || true
    if [ -n "$quota" ] && [ "$quota" != "max" ] && [ -n "$period" ] && [ "${period:-0}" -gt 0 ] 2>/dev/null; then
      cores=$(( (quota + period - 1) / period ))
      [ "$cores" -lt 1 ] && cores=1
      echo "$cores"
      return
    fi
  fi
  if [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ] && [ -r /sys/fs/cgroup/cpu/cpu.cfs_period_us ]; then
    quota=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
    period=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)
    if [ "${quota:-0}" -gt 0 ] && [ "${period:-0}" -gt 0 ]; then
      cores=$(( (quota + period - 1) / period ))
      [ "$cores" -lt 1 ] && cores=1
      echo "$cores"
      return
    fi
  fi
  nproc 2>/dev/null || echo 1
}

CPU_CORES=$(detect_cpu_quota)

if [ -z "${GUNICORN_WORKERS}" ]; then
  AUTO=$((CPU_CORES * 2 + 1))
  [ "$AUTO" -gt 2 ] && AUTO=2
  [ "$AUTO" -lt 1 ] && AUTO=1
  GUNICORN_WORKERS=$AUTO
fi
GUNICORN_THREADS=${GUNICORN_THREADS:-2}

# 60 s is a safer production default; long-running tasks should be queued.
# Override via GUNICORN_TIMEOUT env var if you have legitimate slow endpoints.
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-60}

# Graceful worker recycling: each worker restarts after ~1000 requests
# (random jitter ±100 prevents thundering-herd restarts).
# This reclaims Python memory fragmentation without dropping connections.
GUNICORN_MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-1000}
GUNICORN_MAX_REQUESTS_JITTER=${GUNICORN_MAX_REQUESTS_JITTER:-100}

echo "─────────────────────────────────────────────────"
echo "Gunicorn startup"
echo "  workers     : ${GUNICORN_WORKERS}  (cgroup/quota cores: ${CPU_CORES})"
echo "  threads     : ${GUNICORN_THREADS}"
echo "  timeout     : ${GUNICORN_TIMEOUT}s"
echo "  max-requests: ${GUNICORN_MAX_REQUESTS} ± ${GUNICORN_MAX_REQUESTS_JITTER}"
echo "─────────────────────────────────────────────────"

exec /home/frappe/frappe-bench/env/bin/gunicorn \
  --chdir=/home/frappe/frappe-bench/sites \
  --bind=0.0.0.0:8000 \
  --threads="${GUNICORN_THREADS}" \
  --workers="${GUNICORN_WORKERS}" \
  --worker-class=gthread \
  --worker-tmp-dir=/dev/shm \
  --timeout="${GUNICORN_TIMEOUT}" \
  --max-requests="${GUNICORN_MAX_REQUESTS}" \
  --max-requests-jitter="${GUNICORN_MAX_REQUESTS_JITTER}" \
  --preload \
  frappe.app:application
