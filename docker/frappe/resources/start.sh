#!/bin/bash
set -e

# ── Gunicorn configuration ───────────────────────────────────────────────────
# Workers: auto-scaled to (2 × CPU_cores + 1) unless explicitly set.
# This formula keeps all cores busy under the gthread model.
CPU_CORES=$(nproc 2>/dev/null || echo 1)
GUNICORN_WORKERS=${GUNICORN_WORKERS:-$((CPU_CORES * 2 + 1))}
GUNICORN_THREADS=${GUNICORN_THREADS:-4}

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
echo "  workers     : ${GUNICORN_WORKERS}  (${CPU_CORES} CPU cores × 2 + 1)"
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
